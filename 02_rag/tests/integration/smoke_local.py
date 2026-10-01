"""Integración local explícita, con trazas nuevas y expectativas por caso."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

TOPIC = Path(__file__).resolve().parents[2]
SOURCE = TOPIC / "src"
sys.path.insert(0, str(SOURCE))

from openai import OpenAI, OpenAIError
from context import is_abstention
from documents import load_questions
from embeddings import Embedder
from evaluation import key_present
from model_config import load_local_env, make_backend
from settings import OUTPUTS, ROLES, TRACES
from trace_log import Trace, redact

CUSTODY = "¿Qué repositorios tienen custodia especial?"
CASES = [
    ("01_rag_basico", ["--sin-comparar"]),
    ("02_rag_avanzado", []),
    ("02_rag_avanzado", ["--pregunta", CUSTODY, "--rol", "analista"]),
    ("02_rag_avanzado", ["--pregunta", CUSTODY, "--rol", "seguridad"]),
    ("02_rag_avanzado", ["--pregunta", "¿En cuánto tiempo se paga una amortización aprobada?"]),
    ("03_evaluacion", []),
    ("03_evaluacion", ["--reescritura"]),
]


def validate_records(lesson: str, arguments: list[str], records: list[dict]) -> dict:
    starts = [row for row in records if row["event"] == "run_start"]
    ends = [row for row in records if row["event"] == "run_end"]
    if len(starts) != 1 or starts[0]["backend"] != "local" or len(ends) != 1:
        raise ValueError("Se necesita una única ejecución local.")
    end = ends[0]
    if end.get("completed") is not True or not any(row["event"] == "embedding_response" for row in records):
        raise ValueError("Faltan comprobaciones completadas o embeddings reales.")
    responses = [row for row in records if row["event"] == "model_response"]
    if lesson == "03_evaluacion":
        if bool(responses) != ("--reescritura" in arguments):
            raise ValueError("El uso del modelo de lenguaje no coincide con el modo de evaluación.")
        expected = {"A", "B", "C", "D", "E"} if responses else {"A", "B", "C", "D"}
        summary = end.get("retrieval", {})
        if set(summary) != expected:
            raise ValueError("Configuraciones de evaluación incompletas.")
        for name in expected:
            metrics = summary[name]
            for key in ("hit@1", "hit@3", "mrr@5"):
                value = metrics.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    raise ValueError("Métrica fuera de rango o con tipo incorrecto.")
            if name != "A" and (metrics.get("fugas") != 0 or metrics.get("externos") != 0):
                raise ValueError("Una configuración protegida expuso fuentes no permitidas.")
        return end
    if not responses or not isinstance(end.get("respuesta"), str) or not end["respuesta"].strip():
        raise ValueError("No hay evidencia de una respuesta del modelo real.")
    if lesson == "01_rag_basico":
        if type(end.get("hits")) is not int or not 1 <= end["hits"] <= 3:
            raise ValueError("Recuperación básica fuera del límite.")
        return end
    if lesson != "02_rag_avanzado":
        raise ValueError(f"Lección desconocida: {lesson}")
    if any(type(end.get(key)) is not int or not 0 <= end[key] <= 2 for key in ("searches", "generations")):
        raise ValueError("El grafo excedió sus topes.")
    gold = {question["id"]: question for question in load_questions()}
    if CUSTODY in arguments:
        question = gold["q10"] if "seguridad" in arguments else gold["q11"]
    elif "--pregunta" in arguments:
        question = gold["q05"]
    else:
        question = gold["q02"]
    text = end["respuesta"]
    if question["evidencia"] is None:
        if end.get("status") != "sin_evidencia" or not is_abstention(text):
            raise ValueError("El analista no se abstuvo ante la pregunta reservada.")
    elif end.get("status") != "verificada" or not all(key_present(text, key) for key in question["claves"]):
        raise ValueError("El avanzado no verificó las claves esperadas.")
    if any(key_present(text, key) for key in question["prohibidas"]):
        raise ValueError("La respuesta contiene un dato prohibido.")
    role = question["rol"]
    for row in records:
        if row["event"] == "node" and row.get("name") == "recuperar":
            for hit in row["hits"]:
                chunk = hit["chunk"]
                if chunk["quarantined"] or chunk["classification"] not in ROLES[role]:
                    raise ValueError("La recuperación no respetó permisos o cuarentena.")
    return end


def run_case(lesson: str, arguments: list[str]) -> dict:
    before = set(TRACES.glob(f"{lesson}_*.jsonl"))
    result = subprocess.run([sys.executable, str(SOURCE / f"{lesson}.py"), "--backend", "local", *arguments],
                            cwd=TOPIC, env={**os.environ, "LLM_BACKEND": "local", "PYTHONUTF8": "1"},
                            capture_output=True, text=True, encoding="utf-8", timeout=360)
    if result.returncode:
        raise ValueError(f"{lesson} terminó con código {result.returncode}:\n"
                         + redact((result.stdout + result.stderr)[-4000:]))
    created = set(TRACES.glob(f"{lesson}_*.jsonl")) - before
    if len(created) != 1:
        raise ValueError("No se identificó una traza nueva única.")
    path = created.pop()
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    end = validate_records(lesson, arguments, records)
    return {"lesson": lesson, "arguments": arguments, "passed": True,
            "trace": str(path.relative_to(TOPIC)), "result": end}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True, help="Autorizar inferencia local real.")
    parser.parse_args()
    report = {"time": datetime.now(timezone.utc).isoformat(), "completed": False, "cases": []}
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    preflight = None
    try:
        load_local_env()
        backend = make_backend("local")
        preflight = Trace("integration_preflight", "local", backend.model)
        embedder = Embedder(preflight)
        for url, model in ((backend.base_url, backend.model), (embedder.base_url, embedder.model)):
            with OpenAI(base_url=url, api_key="lm-studio", timeout=10.0, max_retries=0) as client:
                if model not in {item.id for item in client.models.list().data}:
                    raise ValueError(f"El servidor no ofrece {model}. Preparar el modelo antes de probar.")
        embedder.client.close()
        preflight.end(completed=True)
        preflight = None
        for lesson, arguments in CASES:
            report["cases"].append(run_case(lesson, arguments))
            print(f"OK: {lesson} {' '.join(arguments)}", flush=True)
        report["completed"] = True
    except (OpenAIError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        if preflight is not None:
            preflight.end(completed=False, reason=type(exc).__name__)
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
        print(f"ERROR: {report['error']}", file=sys.stderr)
    path = OUTPUTS / "integration_result.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Informe local: {path}")
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
