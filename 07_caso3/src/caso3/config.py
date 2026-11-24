"""Rutas independientes del directorio actual y proveedor de modelo explícito."""
import os
from pathlib import Path
import sys
import time

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
OUTPUTS = ROOT / "outputs"
PROMPTS = ROOT / "prompts"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_ROUNDS = 2
RATE_LIMIT_RETRIES = 8
MAX_RATE_LIMIT_WAIT = 90


def _setting(*keys, default=""):
    for source in (os.environ, dotenv_values(ROOT / ".env")):
        for key in keys:
            if key in source:
                return (source[key] or "").strip()
    return default


def create_model(model_name: str | None = None):
    from langchain_openai import ChatOpenAI

    backend = provider()
    name = resolve_model_name(model_name)
    if backend in {"lm_studio", "local"}:
        if backend == "lm_studio":
            url_key = "LM_STUDIO_BASE_URL"
            base_url = _setting(url_key, default="http://127.0.0.1:1234/v1")
            options = dict(api_key=_setting("LM_STUDIO_API_KEY") or "lm-studio", timeout=120)
        else:
            url_key = "LOCAL_BASE_URL"
            base_url = _setting(url_key)
            options = dict(api_key="local", timeout=float(_setting("LOCAL_TIMEOUT", default="600")),
                           reasoning_effort=_setting("LOCAL_REASONING_EFFORT") or None,
                           streaming=True, stream_usage=True)
        if not base_url:
            raise ValueError(f"Falta {url_key} para conectar con LM Studio.")
        return ChatOpenAI(model=name, base_url=base_url, temperature=0, max_retries=0, **options)

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

    key = _setting("GROQ_API_KEY")
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
    value = _setting("CASO3_MODEL_PROVIDER", "MODEL_PROVIDER", default="groq").lower()
    if value not in {"groq", "lm_studio", "local"}:
        raise ValueError(f"Proveedor de modelo desconocido: {value!r}. Use groq, lm_studio o local.")
    return value


def resolve_model_name(model_name: str | None = None) -> str:
    if model_name:
        return model_name
    backend = provider()
    if backend == "lm_studio":
        return _setting("LM_STUDIO_MODEL", default=DEFAULT_MODEL)
    if backend == "local":
        name = _setting("LOCAL_MODEL")
        if not name:
            raise ValueError("Falta LOCAL_MODEL para MODEL_PROVIDER=local.")
        return name
    return _setting("GROQ_MODEL", default=DEFAULT_MODEL)
