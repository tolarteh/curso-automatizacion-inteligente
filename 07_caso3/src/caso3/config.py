"""Rutas independientes del directorio actual y proveedor de modelo explícito."""
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
OUTPUTS = ROOT / "outputs"
PROMPTS = ROOT / "prompts"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_ROUNDS = 2
RATE_LIMIT_RETRIES = 8
MAX_RATE_LIMIT_WAIT = 90


def create_model(model_name: str | None = None):
    import openai
    from langchain_openai import ChatOpenAI

    class GroqChat(ChatOpenAI):
        # Solo el 429 por tokens/minuto se reintenta; cualquier otro error sigue visible.
        def _generate(self, *args, **kwargs):
            for attempt in range(RATE_LIMIT_RETRIES + 1):
                try:
                    return super()._generate(*args, **kwargs)
                except openai.RateLimitError as error:
                    wait = float(error.response.headers.get("retry-after", 15))
                    if attempt == RATE_LIMIT_RETRIES or wait > MAX_RATE_LIMIT_WAIT:
                        raise
                    print(f"Groq 429: límite de cuota, espera {wait:.0f} s "
                          f"(reintento {attempt + 1}/{RATE_LIMIT_RETRIES}).", file=sys.stderr)
                    time.sleep(wait)

    name = resolve_model_name(model_name)
    if provider() == "local":
        base_url = os.environ.get("LOCAL_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("Falta LOCAL_BASE_URL para MODEL_PROVIDER=local.")
        effort = os.environ.get("LOCAL_REASONING_EFFORT", "").strip() or None
        # El streaming permite ver el progreso token a token; Groq no lo usa para conservar su reintento.
        return ChatOpenAI(model=name, api_key="local", base_url=base_url, temperature=0,
                          reasoning_effort=effort, max_retries=0, streaming=True, stream_usage=True,
                          timeout=float(os.environ.get("LOCAL_TIMEOUT", "600")))
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("Falta GROQ_API_KEY. Configure el entorno o el .env del tema.")
    return GroqChat(
        model=name,
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        temperature=0,
        max_retries=0,
        timeout=120,
    )


def provider() -> str:
    load_dotenv(ROOT / ".env", override=False)
    value = os.environ.get("MODEL_PROVIDER", "groq").strip().lower()
    if value not in {"groq", "local"}:
        raise ValueError(f"MODEL_PROVIDER desconocido: {value!r}. Use groq o local.")
    return value


def resolve_model_name(model_name: str | None = None) -> str:
    if model_name:
        return model_name
    if provider() == "local":
        name = os.environ.get("LOCAL_MODEL", "").strip()
        if not name:
            raise ValueError("Falta LOCAL_MODEL para MODEL_PROVIDER=local.")
        return name
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
