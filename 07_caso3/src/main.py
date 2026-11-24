"""Menú del caso 3: una actividad, un proceso y el mismo intérprete."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ACTIVITIES = (
    ("leccion_local.py", "Normalizar datos y comparar reglas vigentes, sin modelo"),
    ("run_case.py", "Revisar E01 con Deep Agents y detenerse para firma humana"),
    ("run_evals.py", "Evaluar con Groq: componentes y punta a punta, consume cuota"),
    ("estudiante/comprobar.py", "Comprobar el reto de cuatro ejercicios en parejas"),
)


def main():
    for index, (_, label) in enumerate(ACTIVITIES, 1):
        print(f"{index}. {label}")
    print("0. Salir")
    choice = input("Actividad: ").strip()
    if choice == "0":
        return 0
    if not choice.isdigit() or not 1 <= int(choice) <= len(ACTIVITIES):
        print("Error: opción inválida.", file=sys.stderr)
        return 2
    script, _ = ACTIVITIES[int(choice) - 1]
    return subprocess.run([sys.executable, str(ROOT / script)], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
