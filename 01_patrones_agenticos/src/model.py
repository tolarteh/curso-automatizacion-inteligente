"""Cliente real del modelo: la selección de proveedor siempre es explícita."""
import argparse
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from settings import DATABASE, TOPIC
from trace_log import Trace


@dataclass(frozen=True)
class Backend:
    name: str
    base_url: str
    model: str
    api_key: str
    reasoning_effort: str | None


def load_local_env() -> None:
    path = TOPIC / ".env"
    if path.is_file():
        with path.open(encoding="utf-8") as stream:
            load_dotenv(stream=stream, override=False)


def make_backend(name: str) -> Backend:
    if name == "local":
        base_url = os.environ.get("LOCAL_BASE_URL", "http://localhost:1234/v1")
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("LOCAL_BASE_URL debe apuntar al servidor de esta máquina.")
        return Backend(name, base_url, os.environ.get("LOCAL_MODEL", "demo-local"),
                       "lm-studio", os.environ.get("LOCAL_REASONING_EFFORT", "none") or None)
    if name == "groq":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise ValueError("Falta GROQ_API_KEY. Configura el .env local, no el código.")
        base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        if urlparse(base_url).scheme != "https":
            raise ValueError("El backend remoto requiere HTTPS.")
        return Backend(name, base_url, os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"),
                       key, os.environ.get("GROQ_REASONING_EFFORT", "low") or None)
    raise ValueError(f"Backend desconocido: {name}")


def start(description: str, extra=None):
    load_local_env()
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--backend", choices=("local", "groq"),
                        default=os.environ.get("LLM_BACKEND", "local"))
    if extra:
        extra(parser)
    args = parser.parse_args()
    if not DATABASE.is_file():
        parser.error("Falta la base sintética. Ejecuta src\\seed.py desde este tema.")
    try:
        backend = make_backend(args.backend)
    except ValueError as exc:
        parser.error(str(exc))
    return args, backend


class Llm:
    def __init__(self, backend: Backend, trace: Trace):
        self.backend = backend
        self.trace = trace
        self.client = OpenAI(base_url=backend.base_url, api_key=backend.api_key,
                             timeout=30.0, max_retries=0)

    def chat(self, messages: list[dict], *, purpose: str, **kwargs):
        kwargs.setdefault("temperature", 0.2)
        if self.backend.reasoning_effort:
            kwargs.setdefault("reasoning_effort", self.backend.reasoning_effort)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.backend.model, messages=messages, **kwargs)
        except OpenAIError as exc:
            self.trace.show("ERROR DEL MODELO", f"{type(exc).__name__}: {exc}\n"
                            "No se cambia de proveedor ni se reintenta automáticamente.")
            self.trace.end(completed=False, reason="error del modelo")
            raise SystemExit(2) from exc
        if not response.choices:
            raise ValueError("El modelo no devolvió alternativas.")
        choice = response.choices[0]
        if choice.finish_reason in ("length", "content_filter"):
            raise ValueError(f"Respuesta incompleta: {choice.finish_reason}.")
        message = choice.message
        self.trace.emit("model_response", purpose=purpose,
                        seconds=round(time.perf_counter() - started, 2),
                        finish_reason=choice.finish_reason, content=message.content,
                        tool_calls=[{"id": call.id, "name": call.function.name,
                                     "arguments": call.function.arguments}
                                    for call in (message.tool_calls or [])])
        return response
