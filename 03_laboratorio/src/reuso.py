"""Reutiliza el código del tema 01 sin copiarlo ni modificarlo.

La carpeta src del tema 01 se agrega al FINAL de sys.path. Así `import sql_readonly`,
`import trace_log`, `import model` o `import lesson_utils` cargan los archivos del tema 01,
mientras que `settings` y `main` siguen siendo los de este laboratorio (su carpeta va primero).

Qué se reutiliza y por qué:
- model.make_backend: el mismo backend groq/local, elegido siempre de forma explícita.
- trace_log.Trace: el mismo formato JSONL y el mismo enmascarado de secretos.
- sql_readonly: las herramientas y los controles del caso 1 (el permiso lo decide la tool).
- lesson_utils.evaluate_rows y seed: la referencia verificable del caso 1.

Por eso este laboratorio no puede tener archivos con esos nombres (ver tests/test_reuso.py).
"""
import sys

from settings import SOURCE_01

if str(SOURCE_01) not in sys.path:
    sys.path.append(str(SOURCE_01))

# Módulos del tema 01 que no deben repetirse en este laboratorio.
RESERVADOS = ("model", "sql_readonly", "trace_log", "lesson_utils", "seed", "planning_contract")
