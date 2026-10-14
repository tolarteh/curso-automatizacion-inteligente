"""Menú: un proceso independiente por lección."""
from pathlib import Path
import subprocess
import sys

LESSONS = (
    ("01_eventos_y_validacion.py", "Distinguir extracción, evidencia y autorización"),
    ("02_plan_y_aprobacion.py", "Preparar plan versionado y dos aprobaciones"),
    ("03_ejecucion_y_cierre.py", "Verificar cambios simulados y reconciliar fallos"),
)

if __name__ == "__main__":
    for index, (_, objective) in enumerate(LESSONS, start=1):
        print(f"{index}. {objective}")
    print("0. Salir")
    try:
        choice = int(input("Lección: "))
    except ValueError:
        sys.exit("Opción inválida.")
    if choice == 0:
        sys.exit(0)
    if choice not in range(1, len(LESSONS) + 1):
        sys.exit("Opción inválida.")
    script = Path(__file__).resolve().parent / LESSONS[choice - 1][0]
    sys.exit(subprocess.run([sys.executable, str(script)]).returncode)
