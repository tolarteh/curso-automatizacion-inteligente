"""Rutas y periodo de los datos sintéticos, independientes de la terminal."""
from pathlib import Path

TOPIC = Path(__file__).resolve().parents[1]
OUTPUTS = TOPIC / "outputs"
DATABASE = OUTPUTS / "demo.sqlite"
EXPECTED = TOPIC / "data" / "fixtures" / "expected.json"
PROMPTS = TOPIC / "prompts"
TRACES = OUTPUTS / "traces"
PERIOD_START = "2026-03-01"
PERIOD_END = "2026-04-01"
CUTOFF = "2026-04-05"
