"""Opt-in: una llamada real de extracción, nunca Git real."""
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from contracts import ROOT, read_json
from extraction import extract, validate_evidence

if __name__ == "__main__":
    if os.getenv("RUN_MODEL_INTEGRATION") != "1":
        sys.exit("Pendiente: requiere nueva autorización y RUN_MODEL_INTEGRATION=1.")
    event = read_json(ROOT / "data" / "messages.json")[1]
    result, stats = extract(event)
    validated = validate_evidence(event, result)
    expected = read_json(ROOT / "data" / "labels.json")[event["id"]]
    assert all(validated[key] == value for key, value in expected.items())
    print({"extraction_exact": 1, **stats})
