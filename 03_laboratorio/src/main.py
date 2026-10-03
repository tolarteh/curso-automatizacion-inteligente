"""Menú del laboratorio: la escalera de frameworks en tres casos. Cada opción ejecuta una lección."""
from pathlib import Path
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
LESSONS = {
    "1": ("Caso 3 · sin framework", "Soportes de amortización en un ZIP: cadena de pasos fija en Python plano.",
          "01_caso3_zip.py", []),
    "2": ("Caso 1 · LangChain", "Asistente SQL de solo lectura con create_agent (un solo ciclo).",
          "02_caso1_sql.py", []),
    "3": ("Caso 2 · LangGraph", "Correo que dispara una baja en Git, con aprobación humana (buzón simulado).",
          "03_caso2_correo.py", []),
    "4": ("Caso 2 · pendientes", "Hilos detenidos esperando aprobación (sin modelo).",
          "03_caso2_correo.py", ["--pendientes"]),
}
SIN_MODELO = {"4"}


def main() -> int:
    print("Laboratorio: tres casos, una escalera de frameworks")
    print("Las opciones 1 a 3 usan el modelo real configurado en 03_laboratorio/.env.")
    for key, (title, objective, _, _) in LESSONS.items():
        print(f"{key}. {title}: {objective}")
    print("0. Salir sin ejecutar")
    while True:
        try:
            choice = input("Elige una opción: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo se ejecutó ninguna lección.")
            return 0
        if choice == "0":
            return 0
        if choice in LESSONS:
            _, _, script, extra = LESSONS[choice]
            passthrough = [] if choice in SIN_MODELO else sys.argv[1:]
            return subprocess.call([sys.executable, str(SOURCE / script), *extra, *passthrough])
        print("Opción no válida.")


if __name__ == "__main__":
    raise SystemExit(main())
