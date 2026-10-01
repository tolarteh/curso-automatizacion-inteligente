"""Elegir una lección, sin duplicar su configuración ni su lógica."""
import os
from pathlib import Path
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
TOPIC = SOURCE.parent
LESSONS = {
    "1": ("Reflection", "Separar crítica y verificación.", "01_reflection.py"),
    "2": ("Tool use", "Seguir llamadas y comprobar permisos.", "02_tool_use.py"),
    "3": ("Planning", "Validar un plan y revisar antes de continuar.", "03_planning.py"),
}


def main() -> int:
    print("Patrones agénticos")
    print("Las lecciones usan el modelo real configurado en el .env del tema.")
    print("Un proveedor remoto puede consumir cuota. Revisa la configuración antes de elegir.")
    for key, (title, objective, _) in LESSONS.items():
        print(f"{key}. {title}: {objective}")
    print("0. Salir sin ejecutar")

    while True:
        try:
            choice = input("Elige una opción: ").strip()
        except EOFError:
            print("Sin entrada. No se ejecutó ninguna lección.")
            return 0
        except KeyboardInterrupt:
            print("\nCancelado. No se ejecutó ninguna lección.")
            return 130
        if choice == "0":
            return 0
        if choice not in LESSONS:
            print("Opción inválida. Elige 0, 1, 2 o 3.")
            continue
        filename = LESSONS[choice][2]
        command = [sys.executable, str(SOURCE / filename)]
        print(f"Ejecutando {filename}", flush=True)
        try:
            result = subprocess.run(command, cwd=TOPIC,
                                    env={**os.environ, "PYTHONUTF8": "1"}, check=False)
        except OSError as exc:
            print(f"ERROR al iniciar la lección: {exc}", file=sys.stderr)
            return 1
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
