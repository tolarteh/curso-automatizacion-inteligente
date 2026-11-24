"""Publica métricas locales como experimento de Langfuse."""
import os
from pathlib import Path

from dotenv import load_dotenv

from caso3.config import ROOT

_NON_METRICS = {"id", "rep", "agente", "modelo", "error"}


def require_credentials():
    load_dotenv(ROOT / ".env", override=False)
    missing = [key for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if not os.environ.get(key, "").strip()]
    if missing:
        raise ValueError(f"Faltan credenciales de Langfuse: {', '.join(missing)}.")


def verify_trace(client, trace_id):
    observations = client.api.observations.get_many(trace_id=trace_id, limit=1)
    if not observations.data:
        raise RuntimeError(f"Langfuse no confirmó la recepción de la traza {trace_id}.")


def _task(*, item, **kwargs):
    return item["input"]["metricas"]


def _evaluator(name, Evaluation):
    def evaluate(*, output, **kwargs):
        value = output.get(name)
        if value is None:
            return []
        return Evaluation(name=name, value=float(value))

    return evaluate


def publish_experiment(rows, agent, model_name, k, csv_path):
    require_credentials()
    from langfuse import Evaluation, get_client

    metric_names = sorted({
        key
        for row in rows
        for key, value in row.items()
        if key not in _NON_METRICS and isinstance(value, (bool, int, float))
    })
    data = []
    for row in rows:
        metrics = {
            key: row[key]
            for key in metric_names
            if isinstance(row.get(key), (bool, int, float))
        }
        data.append({
            "input": {
                "expediente": row["id"],
                "intento": row["rep"],
                "agente": agent,
                "modelo": model_name,
                "metricas": metrics,
            },
            "metadata": {"source": "07_caso3"},
        })

    client = get_client()
    experiment = client.run_experiment(
        name=Path(csv_path).stem,
        description="Métricas de una evaluación local de 07_caso3.",
        data=data,
        task=_task,
        evaluators=[_evaluator(name, Evaluation) for name in metric_names],
        max_concurrency=1,
        metadata={"agente": agent, "modelo": model_name, "k": str(k)},
    )
    client.flush()
    return experiment
