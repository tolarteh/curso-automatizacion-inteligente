r"""Aserciones de trayectoria y seguridad sobre el grafo LangGraph del Caso 2.

No mira la respuesta final: mira el ESTADO. Usa una carpeta temporal, no toca outputs/.
Uso (PowerShell, desde la raíz): python 05_caso2\evals\trajectory_check.py
"""
import argparse
from pathlib import Path
import sqlite3
import sys
import tempfile

p = argparse.ArgumentParser()
p.add_argument("--repo", default=str(Path.cwd() / "05_caso2"))
args = p.parse_args()
sys.path.insert(0, str(Path(args.repo).resolve() / "src"))
from langgraph.checkpoint.sqlite import SqliteSaver   # noqa: E402
from approval_graph import build_graph                # noqa: E402
from contracts import ControlError, ROOT, digest, read_json  # noqa: E402
import service                                        # noqa: E402

from tracking import Tracker                          # noqa: E402

service.OUTPUT = Path(tempfile.mkdtemp(prefix="caso2-traj-"))
_uri = f"sqlite:///{(service.OUTPUT / 'tracking.db').as_posix()}"   # MLflow local en la carpeta temporal
service.Tracker = lambda case_id, segment, level="metrics": Tracker(case_id, segment, level, test_uri=_uri)
event = read_json(ROOT / "data" / "messages.json")[0]          # mail-001, formulario: 0 llamadas
results = []


def check(name, cond):
    results.append(cond)
    print(f"[{'OK ' if cond else 'MAL'}] {name}")


try:
    case = service.ingest(event, "2026-10-14")
except Exception as exc:
    print(f"Aviso: ingest falló ({type(exc).__name__}: {exc}).")
    sys.exit(1)
git_before = digest(read_json(service.OUTPUT / "git.json"))
config = {"configurable": {"thread_id": f"{case['case_id']}:{case['plan']['version']}"}}
with sqlite3.connect(service.OUTPUT / "checkpoints.sqlite", check_same_thread=False) as db:
    snap = build_graph(SqliteSaver(db)).get_state(config)
check("El grafo quedó detenido en el nodo de aprobación (interrupt antes de Git)", snap.next == ("approval",))
check("Sin aprobaciones registradas tras ingerir", case["approvals"] == [])
try:
    service.run_execution(case["case_id"], "2026-10-14")
    check("Ejecutar sin firmas debe fallar", False)
except ControlError:
    check("Ejecutar sin firmas falla con ControlError", True)
check("Git no cambió sin firmas", digest(read_json(service.OUTPUT / "git.json")) == git_before)
h, v = case["plan"]["hash"], case["plan"]["version"]
service.decide(case["case_id"], "lider-demo", "manager", "approve", h, v)
try:
    service.run_execution(case["case_id"], "2026-10-14")
    check("Ejecutar con una sola firma debe fallar", False)
except ControlError:
    check("Ejecutar con una sola firma falla", True)
check("Git sigue sin cambios con una firma", digest(read_json(service.OUTPUT / "git.json")) == git_before)
# Mismo actor en ambos roles: se prueba sobre una copia con planning.approve, porque un
# intento fallido dentro del grafo deja el checkpoint sin pausa pendiente (habría que replanificar).
import copy                                            # noqa: E402
from planning import approve                           # noqa: E402
try:
    approve(copy.deepcopy(service.load(case["case_id"])), "lider-demo", "security", "approve", h, v)
    check("Mismo actor en ambos roles debe fallar", False)
except ControlError:
    check("Mismo actor en ambos roles falla", True)
service.decide(case["case_id"], "seguridad-demo", "security", "approve", h, v)
final = service.run_execution(case["case_id"], "2026-10-14")
check("Con dos firmas distintas, la ejecución termina", final["status"] == "COMPLETADO")
check("Git cambió solo después de las dos firmas", digest(read_json(service.OUTPUT / "git.json")) != git_before)
print(f"\nTrayectoria: {sum(results)}/{len(results)} aserciones. Carpeta temporal: {service.OUTPUT}")
sys.exit(0 if all(results) else 1)
