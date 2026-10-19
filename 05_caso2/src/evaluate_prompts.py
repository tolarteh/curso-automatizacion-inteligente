"""Comparación acotada de prompts: extracción y política, sin casos ni Git."""
import argparse
import os
import time

from dotenv import load_dotenv
from openai import APIError
from pydantic import ValidationError

from contracts import ALLOWLIST, ControlError, FIELDS, ROOT, digest, read_json, write_json
from extraction import ExtractionResponseError, extract
from extraction import validate_evidence
from planning import validate_request
from tracking import Tracker

EXPERIMENT = "case2-prompt-evaluation"


def candidates():
    base = (ROOT / "prompts" / "extract.txt").read_text(encoding="utf-8")
    return [{"name": item["name"], "prompt": item["template"] if "template" in item
             else base + ("\n" + item["append"] if item["append"] else "")}
            for item in read_json(ROOT / "prompts" / "candidates.json")]


def evaluate_case(item, dataset, prompt, provider):
    event = item["event"]
    result = {"event_id": event["id"], "category": item["category"],
              "expected": item["expected"], "expected_accept": item["accept"],
              "extracted": None, "stats": None, "attempted": False, "outcome": "error",
              "error": None, "error_kind": None, "stage": "sender"}
    start = time.perf_counter()
    if event["sender"] not in ALLOWLIST:
        result.update(outcome="blocked", error="Remitente no permitido.")
    else:
        result.update(stage="extraction", attempted=True)
        try:
            result["extracted"], result["stats"] = extract(event, provider, prompt=prompt)
        except (ValueError, APIError, TimeoutError, ConnectionError) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["error_kind"] = "model_output" if isinstance(exc, ExtractionResponseError) else "operational"
        else:
            result["stage"] = "policy"
            try:
                request = validate_evidence(event, result["extracted"])
                validate_request(request, dataset["personnel"], dataset["today"])
            except (ControlError, ValidationError) as exc:
                result.update(outcome="rejected", error=f"{type(exc).__name__}: {exc}")
            else:
                result["outcome"] = "accepted"
    result["ingestion_latency_ms"] = (time.perf_counter() - start) * 1000
    return result


def summarize(rows):
    attempted = [row for row in rows if row["attempted"]]
    positives = [row for row in rows if row["expected_accept"]]
    negatives = [row for row in rows if not row["expected_accept"]]
    exact = sum(row["extracted"] is not None and all(
        row["extracted"][key] == row["expected"][key] for key in ("intent", *FIELDS))
                for row in attempted)
    correct = sum(row["outcome"] != "error" and
                  (row["outcome"] == "accepted") == row["expected_accept"] for row in rows)
    metrics = {
        "cases": len(rows), "calls_attempted": len(attempted),
        "extraction_exact": exact / len(attempted),
        "intent_accuracy": sum(row["extracted"] is not None and
                               row["extracted"]["intent"] == row["expected"]["intent"]
                               for row in attempted) / len(attempted),
        "json_valid_rate": sum(row["extracted"] is not None for row in attempted) / len(attempted),
        "policy_accuracy": correct / len(rows),
        "valid_accept_rate": sum(row["outcome"] == "accepted" for row in positives) / len(positives),
        "false_accept_count": sum(row["outcome"] == "accepted" for row in negatives),
        "false_accept_rate": sum(row["outcome"] == "accepted" for row in negatives) / len(negatives),
        "errors": sum(row["outcome"] == "error" for row in rows),
        "model_output_errors": sum(row.get("error_kind") == "model_output" for row in rows),
        "operational_errors": sum(row["outcome"] == "error" and row.get("error_kind") != "model_output"
                                  for row in rows),
        "tokens_known": sum(row["stats"]["tokens"] for row in rows if row["stats"] is not None),
        "usage_unknown_calls": sum(row["attempted"] and row["stats"] is None for row in rows),
        "ingestion_latency_ms_mean": sum(row["ingestion_latency_ms"] for row in rows) / len(rows),
    }
    for field in FIELDS:
        metrics[f"accuracy_{field}"] = sum(
            row["extracted"] is not None and row["extracted"][field] == row["expected"][field]
            for row in attempted) / len(attempted)
    return metrics


def validate_inputs(dataset, prompts):
    if len(prompts) != 5 or len({digest(item["prompt"]) for item in prompts}) != 5:
        raise ControlError("Se requieren cinco prompts distintos.")
    cases = dataset["cases"]
    if len(cases) != 12 or len({item["event"]["id"] for item in cases}) != 12:
        raise ControlError("Se requieren doce correos distintos.")
    if not any(item["accept"] for item in cases) or not any(not item["accept"] for item in cases):
        raise ControlError("El corpus requiere casos aceptados y rechazados.")
    for item in cases:
        if set(item["expected"]) != {"intent", *FIELDS} or type(item["accept"]) is not bool:
            raise ControlError("Etiqueta fuera del contrato de evaluación.")
        if item["event"]["body"].startswith("BAJA\n"):
            raise ControlError("El corpus de prompts debe usar prosa, no el bypass de formulario.")
    if not any(item["event"]["sender"] in ALLOWLIST for item in cases):
        raise ControlError("No hay correos elegibles para extracción.")


def run(provider):
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("ALLOW_MODEL_CALLS") != "1" or os.getenv("SYNTHETIC_TRACES") != "1":
        raise ControlError("Requiere ALLOW_MODEL_CALLS=1 y SYNTHETIC_TRACES=1.")
    prompts, dataset = candidates(), read_json(ROOT / "data" / "prompt_eval.json")
    validate_inputs(dataset, prompts)
    # Reutilizar la validación de servidor local y credenciales, sin abrir un run de caso.
    mlflow = Tracker("prompt-evaluation", "configuration", "traces").mlflow
    mlflow.set_experiment(EXPERIMENT)
    mlflow.set_registry_uri(mlflow.get_tracking_uri())
    mlflow.langchain.autolog(log_traces=True, silent=False)
    try:
        with mlflow.start_run(run_name="five-prompts") as batch:
            batch_id = batch.info.run_id
            output = ROOT / "outputs" / "prompt-evaluation" / batch_id
            write_json(output / "dataset.json", dataset)
            mlflow.log_artifact(str(output / "dataset.json"))
            mlflow.log_params({"provider": provider, "dataset_hash": digest(dataset),
                               "prompts": 5, "cases_per_prompt": 12, "max_calls": 60,
                               "today": dataset["today"], "selection_set": "development",
                               "min_call_interval_seconds": 10})
            summaries = []
            last_call = None
            for candidate in prompts:
                with mlflow.start_run(run_name=candidate["name"], nested=True) as child:
                    registered = mlflow.genai.register_prompt(
                        name="case2-extraction", template=candidate["prompt"],
                        commit_message=candidate["name"])
                    prompt_uri = f"prompts:/{registered.name}/{registered.version}"
                    loaded = mlflow.genai.load_prompt(prompt_uri)
                    mlflow.log_params({"candidate": candidate["name"], "prompt_uri": prompt_uri,
                                       "prompt_hash": digest(candidate["prompt"]),
                                       "provider": provider})
                    rows = []
                    for item in dataset["cases"]:
                        if item["event"]["sender"] in ALLOWLIST:
                            if last_call is not None:
                                time.sleep(max(0, 10 - (time.monotonic() - last_call)))
                            last_call = time.monotonic()
                        with mlflow.start_span(name="evaluate_ingestion") as span:
                            span.set_inputs({"event": item["event"], "candidate": candidate["name"]})
                            row = evaluate_case(item, dataset, loaded.template, provider)
                            span.set_outputs(row)
                        rows.append(row)
                        print(f"{candidate['name']} / {row['event_id']}: {row['outcome']}"
                              + (f" | {row['error']}" if row["error"] else ""), flush=True)
                        if row["stats"]:
                            mlflow.log_param("model", row["stats"]["model"])
                    metrics = summarize(rows)
                    mlflow.log_metrics(metrics)
                    mlflow.set_tag("evaluation_status",
                                   "complete" if metrics["operational_errors"] == 0 else "incomplete")
                    summary = {"candidate": candidate["name"], "run_id": child.info.run_id,
                               "prompt_uri": prompt_uri, "metrics": metrics}
                    path = output / f"{candidate['name']}.json"
                    write_json(path, {"summary": summary, "prompt": candidate["prompt"], "results": rows})
                    mlflow.log_artifact(str(path))
                    summaries.append(summary)
            write_json(output / "comparison.json", summaries)
            mlflow.log_artifact(str(output / "comparison.json"))
            comparable = all(item["metrics"]["operational_errors"] == 0 for item in summaries)
            mlflow.set_tag("comparable", str(comparable).lower())
            if not comparable:
                print("COMPARACIÓN INCOMPLETA: hubo errores operativos; no elegir ganador.", flush=True)
            print(f"Comparación: {output / 'comparison.json'}", flush=True)
            print(f"MLflow batch: {batch_id}", flush=True)
    finally:
        mlflow.langchain.autolog(disable=True)
        mlflow.flush_trace_async_logging()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["groq", "local"], default="groq")
    args = parser.parse_args()
    run(args.provider)
