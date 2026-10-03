"""Arranque común de los tres casos: .env del laboratorio, backend explícito y errores legibles.

Reutiliza model.py del tema 01 (backends groq/local). Aquí solo se agregan el cliente de
LangChain con topes (casos 1 y 2) y el mensaje del 429 con qué hacer.
"""
import argparse
import os

import openai

import reuso  # noqa: F401  (habilita los módulos del tema 01)
from model import Backend, load_local_env, make_backend  # tema 01

MODEL_TIMEOUT = 30.0
# Tope de salida por llamada. En el plan gratuito de Groq la cuota por minuto se reserva con
# max_tokens: sin tope, los modelos con poca cuota de salida se rechazan antes de responder.
MAX_OUTPUT_TOKENS = 600
RATE_LIMIT_HINT = ("Límite por minuto del plan gratuito de Groq: espera un minuto y repite. "
                   "No se reintenta ni se cambia de proveedor automáticamente.")


def parser(description: str) -> argparse.ArgumentParser:
    """Lee el .env de 03_laboratorio (las variables de la terminal ganan) y ofrece --backend."""
    load_local_env()  # tema 01: usa settings.TOPIC, es decir, 03_laboratorio/.env
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--backend", choices=("local", "groq"),
                        default=os.environ.get("LLM_BACKEND", "local"))
    return result


def backend_from(args, parse: argparse.ArgumentParser) -> Backend:
    try:
        return make_backend(args.backend)
    except ValueError as exc:
        parse.error(str(exc))


def chat_model(backend: Backend):
    """ChatOpenAI sobre el mismo endpoint compatible con OpenAI: solo cambian URL, modelo y clave."""
    from langchain_openai import ChatOpenAI  # el caso 3 (sin framework) no lo necesita
    extra = {"reasoning_effort": backend.reasoning_effort} if backend.reasoning_effort else {}
    return ChatOpenAI(model=backend.model, base_url=backend.base_url, api_key=backend.api_key,
                      temperature=0, timeout=MODEL_TIMEOUT, max_retries=0,
                      max_tokens=MAX_OUTPUT_TOKENS, **extra)


def explain(exc: BaseException) -> str:
    """Texto del error para pantalla y traza; el 429 de cuota trae qué hacer."""
    text = f"{type(exc).__name__}: {exc}"
    return f"{text}\n{RATE_LIMIT_HINT}" if isinstance(exc, openai.RateLimitError) else text


def is_tool_use_failed(exc: BaseException) -> bool:
    """El 400 de Groq cuando el modelo insiste en una herramienta que ya no puede usar."""
    return isinstance(exc, openai.BadRequestError) and getattr(exc, "code", None) == "tool_use_failed"


def ejecutar(main) -> int:
    """Corre una lección. Si un TODO del reto sigue sin resolver, lo dice en una línea (sin traza larga)."""
    try:
        return main()
    except NotImplementedError as exc:
        print(f"\nPENDIENTE: {exc}\nCompleta ese TODO y vuelve a ejecutar. Las pruebas sin modelo: "
              "python 03_laboratorio\\tests\\run_cpu.py --caso <n>")
        return 3
