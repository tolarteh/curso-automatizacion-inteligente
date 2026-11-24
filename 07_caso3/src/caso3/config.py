"""Rutas independientes del directorio actual y cliente Groq explícito."""
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
    from langchain_openai import ChatOpenAI

    load_dotenv(ROOT / ".env", override=False)
    provider = os.environ.get("CASO3_MODEL_PROVIDER", "groq").strip().lower()
    if provider == "lm_studio":
        base_url = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").strip()
        if not base_url:
            raise ValueError("Falta LM_STUDIO_BASE_URL para conectar con LM Studio.")
        return ChatOpenAI(
            model=model_name or os.environ.get("LM_STUDIO_MODEL", DEFAULT_MODEL),
            api_key=os.environ.get("LM_STUDIO_API_KEY", "lm-studio").strip() or "lm-studio",
            base_url=base_url,
            temperature=0,
            max_retries=0,
            timeout=120,
        )
    if provider != "groq":
        raise ValueError(f"Proveedor de modelo desconocido: {provider}. Use groq o lm_studio.")

    import openai

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

    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("Falta GROQ_API_KEY. Configure el entorno o el .env del tema.")
    return GroqChat(
        model=model_name or os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        temperature=0,
        max_retries=0,
        timeout=120,
    )
