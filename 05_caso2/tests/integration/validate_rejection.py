"""Una llamada real: rechazo auditado sin permisos ni cambios."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from dotenv import load_dotenv
from contracts import ControlError, ROOT, Status, digest, read_json, write_json
import service


def validate(provider):
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("RUN_MODEL_INTEGRATION") != "1":
        raise ControlError("Requiere autorización y RUN_MODEL_INTEGRATION=1.")
    output = ROOT / "outputs" / "integration" / f"rejection-{provider}-{uuid.uuid4().hex[:12]}"
    service.OUTPUT = output
    event = read_json(ROOT / "data" / "messages.json")[4]
    event = dict(event, id=f"{event['id']}-{uuid.uuid4().hex}")
    inventory = read_json(service.initialize_inventory())
    evidence = {"provider": provider, "success": False, "case_id": digest(event["id"])}
    try:
        try:
            service.ingest(event, "2026-10-14", "traces", provider)
        except ControlError as exc:
            evidence["rejection"] = str(exc)
        else:
            raise AssertionError("La injection no fue rechazada explícitamente.")
        case = service.load(evidence["case_id"])
        assert case["status"] == Status.REJECTED
        assert not case["approvals"] and not case["journal"] and "plan" not in case
        assert read_json(output / "git.json") == inventory
        audit = [json.loads(line) for line in (
            service.case_path(case["case_id"]).parent / "audit.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        assert any(item["event"] == "ingestion_failed" for item in audit)
        import mlflow
        client = mlflow.tracking.MlflowClient()
        experiment = client.get_experiment_by_name("synthetic-offboarding")
        runs = client.search_runs([experiment.experiment_id], f"tags.case_id = '{case['case_id']}'")
        assert len(runs) == 1 and runs[0].info.status == "FAILED"
        traces = mlflow.search_traces(locations=[experiment.experiment_id], return_type="list")
        linked = [trace for trace in traces if
                  trace.info.trace_metadata.get("mlflow.sourceRun") == runs[0].info.run_id]
        assert linked
        evidence.update(success=True, status=case["status"], inventory_unchanged=True,
                        audit=audit, run_id=runs[0].info.run_id,
                        trace_ids=[trace.info.trace_id for trace in linked])
    finally:
        write_json(output / "validation.json", evidence)
        print({"success": evidence["success"], "evidence": str(output / "validation.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("groq", "local"), required=True)
    validate(parser.parse_args().provider)
