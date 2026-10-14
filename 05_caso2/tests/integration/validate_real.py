"""Integración autorizada, con evidencia persistente y sin Git real."""
import argparse
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from dotenv import load_dotenv
from contracts import ControlError, ROOT, Status, read_json, write_json
from extraction import extract, validate_evidence
import service


def validate(provider):
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("RUN_MODEL_INTEGRATION") != "1":
        raise ControlError("Requiere autorización y RUN_MODEL_INTEGRATION=1.")
    output = ROOT / "outputs" / "integration" / f"{provider}-{uuid.uuid4().hex[:12]}"
    output.mkdir(parents=True)
    service.OUTPUT = output
    evidence = {"provider": provider, "output": str(output), "extraction": [], "workflows": []}
    labels = read_json(ROOT / "data" / "labels.json")
    messages = read_json(ROOT / "data" / "messages.json")
    try:
        for event in messages:
            if event["id"] not in labels:
                continue
            try:
                result, stats = extract(event, provider)
            except Exception as exc:
                evidence["extraction"].append({"event": event["id"], "exact": False,
                                               "error_type": type(exc).__name__})
                continue
            expected = labels[event["id"]]
            assert all(result[key] == value for key, value in expected.items()), event["id"]
            if expected["intent"] == "offboard":
                validate_evidence(event, result)
            else:
                try:
                    validate_evidence(event, result)
                except ControlError:
                    pass
                else:
                    raise AssertionError("La política aceptó un mensaje inválido.")
            evidence["extraction"].append({"event": event["id"], "exact": True, **stats})
        for event in messages[:2]:
            source_id = event["id"]
            event = dict(event, id=f"{source_id}-{uuid.uuid4().hex}")
            case = service.ingest(event, "2026-10-14", "traces", provider)
            case_id = case["case_id"]
            inventory = read_json(output / "git.json")
            assert not case["approvals"] and not case["journal"]
            assert service.ingest(event, "2026-10-14", "traces", provider)["case_id"] == case_id
            try:
                service.run_execution(case_id, "2026-10-14", level="traces")
            except ControlError:
                pass
            else:
                raise AssertionError("Ejecución sin aprobación.")
            assert read_json(output / "git.json") == inventory
            for actor, role in (("lider-demo", "manager"), ("seguridad-demo", "security")):
                case = service.decide(case_id, actor, role, "approve",
                                      case["plan"]["hash"], case["plan"]["version"], "traces")
                assert read_json(output / "git.json") == inventory
            case = service.run_execution(case_id, "2026-10-14", level="traces")
            assert case["status"] == Status.DONE
            report = read_json(service.case_path(case_id).parent / "report.json")
            assert not report["pending"]
            assert len(report["verified"]) == len(case["plan"]["actions"])
            assert (service.case_path(case_id).parent / "notification.txt").read_text(
                encoding="utf-8").startswith("BORRADOR LOCAL, NO ENVIADO")
            import mlflow
            client = mlflow.tracking.MlflowClient()
            experiment = client.get_experiment_by_name("synthetic-offboarding")
            runs = client.search_runs([experiment.experiment_id], f"tags.case_id = '{case_id}'")
            traces = mlflow.search_traces(locations=[experiment.experiment_id], return_type="list")
            run_ids = {run.info.run_id for run in runs}
            linked = [trace for trace in traces
                      if trace.info.trace_metadata.get("mlflow.sourceRun") in run_ids]
            assert linked, "No hay trazas reales enlazadas al caso."
            assert any(run.data.tags.get("business_status") == Status.DONE for run in runs)
            evidence["workflows"].append({"event": source_id, "case_id": case_id,
                "status": report["status"], "verified": len(report["verified"]),
                "manual_pending": report["manual_pending"], "run_ids": sorted(run_ids),
                "trace_ids": [trace.info.trace_id for trace in linked]})
        evidence["success"] = all(item["exact"] for item in evidence["extraction"])
        assert evidence["success"], "Extracciones incorrectas, revisar validation.json."
    except Exception as exc:
        evidence.update(success=False, error_type=type(exc).__name__)
        raise
    finally:
        write_json(output / "validation.json", evidence)
        print({"provider": provider, "success": evidence.get("success"),
               "evidence": str(output / "validation.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("groq", "local"), required=True)
    validate(parser.parse_args().provider)
