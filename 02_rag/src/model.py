"""Cliente real: errores visibles, sin reintentos ni cambio de proveedor."""
import json
import time

from openai import OpenAI, OpenAIError
from model_config import Backend
from settings import PROMPTS
from trace_log import Trace


def read_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8").strip()


class Llm:
    def __init__(self, backend: Backend, trace: Trace):
        self.backend = backend
        self.trace = trace
        self.client = OpenAI(base_url=backend.base_url, api_key=backend.api_key,
                             timeout=30.0, max_retries=0)

    def chat(self, messages: list[dict], *, purpose: str, **kwargs) -> str:
        kwargs.setdefault("temperature", 0.1)
        if self.backend.reasoning_effort:
            kwargs.setdefault("reasoning_effort", self.backend.reasoning_effort)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.backend.model, messages=messages, **kwargs)
        except OpenAIError as exc:
            self.trace.show("ERROR DEL MODELO", f"{type(exc).__name__}: {exc}\n"
                            "No se reintenta ni se cambia de proveedor.")
            self.trace.end(completed=False, reason="error del modelo")
            raise SystemExit(2) from exc
        if not response.choices:
            raise ValueError("El modelo no devolvió alternativas.")
        choice = response.choices[0]
        text = choice.message.content
        self.trace.emit("model_response", purpose=purpose, seconds=round(time.perf_counter() - started, 2),
                        finish_reason=choice.finish_reason, messages=messages, content=text)
        if choice.finish_reason in ("length", "content_filter"):
            raise ValueError(f"Respuesta incompleta: {choice.finish_reason}.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("El modelo no devolvió texto.")
        return text.strip()

    def chat_json(self, messages: list[dict], schema: dict, *, name: str, purpose: str) -> dict:
        text = self.chat(messages, purpose=purpose, response_format={
            "type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}})
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("La salida estructurada debe ser un objeto JSON.")
        return result
