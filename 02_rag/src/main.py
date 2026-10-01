"""Elegir una lección sin duplicar su configuración ni sus llamadas."""
import os
from pathlib import Path
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
TOPIC = SOURCE.parent
LESSONS = {
    "1": ("RAG básico", "Observar contexto y limitaciones.", "01_rag_basico.py"),
    "2": ("RAG avanzado", "Seguir permisos y rutas acotadas.", "02_rag_avanzado.py"),
    "3": ("Evaluación", "Medir recuperación y exposición de fuentes.", "03_evaluacion.py"),
}


def main() -> int:
    print("Recuperación aumentada por generación")
    print("Las opciones usan embeddings reales. 1 y 2 también llaman al modelo de lenguaje.")
    print("3 evalúa recuperación sin modelo de lenguaje. Revisa el .env del tema antes de elegir.")
    print("El básico solo permite modelo local. Un proveedor remoto puede consumir cuota.")
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
        command = [sys.executable, str(SOURCE / LESSONS[choice][2])]
        print(f"Ejecutando {LESSONS[choice][2]}", flush=True)
        try:
            result = subprocess.run(command, cwd=TOPIC,
                                    env={**os.environ, "PYTHONUTF8": "1"}, check=False)
        except OSError as exc:
            print(f"ERROR al iniciar la lección: {exc}", file=sys.stderr)
            return 1
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
