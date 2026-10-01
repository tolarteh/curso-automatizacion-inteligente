from pathlib import Path

TOPIC = Path(__file__).resolve().parents[1]
CORPUS = TOPIC / "data" / "corpus"
QUESTIONS = TOPIC / "data" / "evaluacion" / "preguntas.json"
PROMPTS = TOPIC / "prompts"
OUTPUTS = TOPIC / "outputs"
INDEXES = OUTPUTS / "indices"
TRACES = OUTPUTS / "traces"
NO_EVIDENCE = "No encuentro evidencia en los documentos disponibles."
ROLES = {"analista": ("publica", "interna"), "seguridad": ("publica", "interna", "reservada")}
