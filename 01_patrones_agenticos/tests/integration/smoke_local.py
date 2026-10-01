"""Prueba explícita del modelo local real, excluida de las pruebas CPU."""
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
from lesson_utils import expected
from model import load_local_env, make_backend
from seed import expected_result, seed_database
from settings import OUTPUTS, TRACES
from trace_log import redact

CASES = [
    ("01_reflection", []),
    ("02_tool_use", []),
    ("02_tool_use", ["--case", "destructivo"]),
    ("03_planning", ["--aprobar", "n"]),
]


def validate_records(lesson: str, records: list[dict]) -> dict:
    starts = [record for record in records if record["event"] == "run_start"]
    ends = [record for record in records if record["event"] == "run_end"]
    if len(starts) != 1 or starts[0]["backend"] != "local" or len(ends) != 1:
        raise ValueError("La traza no corresponde a una única ejecución local.")
    if not any(record["event"] == "model_response" for record in records):
        raise ValueError("No hay evidencia de una respuesta del modelo real.")
    end = ends[0]
    if end.get("completed") is not True:
        raise ValueError("La ejecución no completó sus comprobaciones.")
    if lesson == "01_reflection":
        corrections = end.get("corrections")
        if end.get("last_passed") is not True or type(corrections) is not int or not 0 <= corrections <= 2:
            raise ValueError("Reflection no verificó la referencia o excedió sus rondas.")
    elif lesson == "02_tool_use":
        minimum = 0 if end.get("case") == "destructivo" else 1
        calls = end.get("tool_calls")
        if end.get("verified") is not True or type(calls) is not int or not minimum <= calls <= 3:
            raise ValueError("Tool use no verificó los datos o el rechazo.")
    elif lesson == "03_planning":
        if end.get("status") != "rejected" or end.get("rows_verified") is not True or end.get("executed_steps") != 2:
            raise ValueError("Planning no se detuvo después de revisar los datos.")
    else:
        raise ValueError(f"Lección desconocida: {lesson}")
    return end


def run_case(lesson: str, arguments: list[str]) -> dict:
    before = set(TRACES.glob(f"{lesson}_*.jsonl"))
    result = subprocess.run([sys.executable, str(SOURCE / f"{lesson}.py"), "--backend", "local", *arguments],
                            cwd=TOPIC, env={**os.environ, "PYTHONUTF8": "1"},
                            capture_output=True, text=True, encoding="utf-8", timeout=240)
    if result.returncode:
        raise ValueError(f"{lesson} terminó con código {result.returncode}:\n"
                         + redact((result.stdout + result.stderr)[-4000:]))
    created = set(TRACES.glob(f"{lesson}_*.jsonl")) - before
    if len(created) != 1:
        raise ValueError("No se identificó una traza nueva única.")
    path = created.pop()
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    end = validate_records(lesson, records)
    return {"lesson": lesson, "arguments": arguments, "passed": True,
            "trace": str(path.relative_to(TOPIC)), "result": end}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="Autorizar llamadas al modelo local y regenerar la base sintética.")
    parser.parse_args()
    report = {"time": datetime.now(timezone.utc).isoformat(), "completed": False, "cases": []}
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    try:
        load_local_env()
        backend = make_backend("local")
        report["model"] = backend.model
        with OpenAI(base_url=backend.base_url, api_key=backend.api_key,
                    timeout=10.0, max_retries=0) as client:
            ids = {item.id for item in client.models.list().data}
        if backend.model not in ids:
            raise ValueError(f"El servidor no ofrece {backend.model}. Habilita ese modelo antes de probar.")
        if expected_result() != expected():
            raise ValueError("Los datos y la referencia independiente no coinciden.")
        seed_database(reset=True)
        for lesson, arguments in CASES:
            outcome = run_case(lesson, arguments)
            report["cases"].append(outcome)
            print(f"OK: {lesson} {' '.join(arguments)}", flush=True)
        report["completed"] = True
    except (OpenAIError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
        print(f"ERROR: {report['error']}", file=sys.stderr)
    path = OUTPUTS / "integration_result.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Informe local: {path}")
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
