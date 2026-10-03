"""Rutas del laboratorio. Todo vive en 03_laboratorio salvo la base del caso 1.

Los módulos que se reutilizan del tema 01 (sql_readonly, trace_log, lesson_utils, model)
importan `settings`; este archivo les entrega las mismas variables: la base y la referencia
del tema 01 (caso 1) y las salidas propias de este laboratorio.
"""
from pathlib import Path

TOPIC = Path(__file__).resolve().parents[1]
REPO = TOPIC.parent
TOPIC_01 = REPO / "01_patrones_agenticos"
SOURCE_01 = TOPIC_01 / "src"

# Caso 1: misma base sintética, misma referencia y mismo criterio que el tema 01.
DATABASE = TOPIC_01 / "outputs" / "demo.sqlite"
EXPECTED = TOPIC_01 / "data" / "fixtures" / "expected.json"
PERIOD_START = "2026-03-01"
PERIOD_END = "2026-04-01"
CUTOFF = "2026-04-05"

PROMPTS = TOPIC / "prompts"
PROMPTS_01 = TOPIC_01 / "prompts"
DATA = TOPIC / "data"
DATA_CASO2 = DATA / "caso2"
DATA_CASO3 = DATA / "caso3"

# Salidas propias del laboratorio, ignoradas por Git (**/outputs/).
OUTPUTS = TOPIC / "outputs"
TRACES = OUTPUTS / "traces"
OUTPUTS_CASO2 = OUTPUTS / "caso2"
OUTPUTS_CASO3 = OUTPUTS / "caso3"
