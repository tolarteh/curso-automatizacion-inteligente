"""Rutas independientes del directorio actual y cliente Groq explícito."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
OUTPUTS = ROOT / "outputs"
PROMPTS = ROOT / "prompts"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_ROUNDS = 2


def create_model(model_name: str | None = None):
    from langchain_openai import ChatOpenAI

    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("Falta GROQ_API_KEY. Configure el entorno o el .env del tema.")
    return ChatOpenAI(
        model=model_name or os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        temperature=0,
        max_retries=0,
        timeout=120,
    )
