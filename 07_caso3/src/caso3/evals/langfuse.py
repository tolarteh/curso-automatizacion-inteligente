"""Publica métricas locales como experimento de Langfuse."""
from contextlib import contextmanager
import os
from pathlib import Path
import time

from dotenv import dotenv_values

from caso3.config import ROOT, provider

_NON_METRICS = {"id", "rep", "agente", "modelo", "error"}


def require_credentials():
    # Activar Langfuse no debe cambiar el proveedor de inferencia seleccionado en la terminal.
    for key, value in dotenv_values(ROOT / ".env").items():
        if key.startswith("LANGFUSE_") and value is not None:
            os.environ.setdefault(key, value)
    missing = [key for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if not os.environ.get(key, "").strip()]
    if missing:
        raise ValueError(f"Faltan credenciales de Langfuse: {', '.join(missing)}.")


def verify_trace(client, trace_id):
    # flush completa el envío, no garantiza que el índice de lectura ya esté actualizado.
    for wait in (0, 1, 2, 4, 8, 15):
        if wait:
            time.sleep(wait)
        if client.api.observations.get_many(trace_id=trace_id, limit=1).data:
            return
    raise RuntimeError(f"Langfuse no confirmó la recepción de la traza {trace_id}. "
                       "Compruebe ese ID antes de repetir la evaluación.")


@contextmanager
def observe_handoff(parent, role):
    # Un span manual evita exportar automáticamente excepciones que incluyan texto documental.
    span = parent.start_observation(name=f"07_caso3.{role}", as_type="agent")
    status = {}
    passed = False
    try:
        yield status
        passed = True
    finally:
        try:
            span.update(level="DEFAULT" if passed else "ERROR",
                        output=dict(contrato_valido=status.get("contrato_valido"),
                                    evidencia_fiel=status.get("evidencia_fiel"), control_superado=passed))
        finally:
            span.end()


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
        metadata={"agente": agent, "modelo": model_name, "proveedor": provider(), "k": str(k)},
    )
    client.flush()
    return experiment
