"""Callback de LangChain que escribe en la traza JSONL del tema 01 (trace_log.Trace).

Registra cada respuesta del modelo (segundos y tokens), cada herramienta y cada nodo
del grafo. Los secretos los enmascara Trace.
"""
import json
import time

import reuso  # noqa: F401
from langchain_core.callbacks import BaseCallbackHandler
from trace_log import Trace  # tema 01: mismo formato y mismo enmascarado

__all__ = ["Trace", "TraceCallback", "node_printer"]


class TraceCallback(BaseCallbackHandler):
    def __init__(self, trace, purpose: str = "agente", clock=time.perf_counter):
        self.trace, self.purpose, self.clock, self.started = trace, purpose, clock, {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self.started[run_id] = self.clock()

    def on_llm_end(self, response, *, run_id, **kwargs):
        seconds = round(self.clock() - self.started.pop(run_id, self.clock()), 2)
        generation = response.generations[0][0]
        message = getattr(generation, "message", None)
        usage = getattr(message, "usage_metadata", None) or {}
        info = getattr(message, "response_metadata", None) or {}
        self.trace.emit("model_response", purpose=self.purpose, seconds=seconds,
                        finish_reason=info.get("finish_reason"),
                        tokens={"entrada": usage.get("input_tokens"), "salida": usage.get("output_tokens"),
                                "total": usage.get("total_tokens")},
                        content=getattr(message, "content", generation.text),
                        tool_calls=[{"name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)}
                                    for call in (getattr(message, "tool_calls", None) or [])])

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.started.pop(run_id, None)
        self.trace.emit("model_error", error=f"{type(error).__name__}: {error}")

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        self.trace.emit("tool_call", name=(serialized or {}).get("name"),
                        arguments=json.dumps(inputs if inputs is not None else input_str, ensure_ascii=False))

    def on_tool_end(self, output, *, run_id, **kwargs):
        content = getattr(output, "content", output)
        try:
            content = json.loads(content)
        except (TypeError, ValueError):
            pass
        self.trace.emit("tool_result", name=getattr(output, "name", None), result=content)


def node_printer(trace, mostrar=True):
    """Para el stream de un grafo: un evento node en la traza y una línea en pantalla."""
    def on_node(name, update):
        keys = sorted(update) if isinstance(update, dict) else []
        trace.emit("node", name=name, escribe=keys)
        if mostrar:
            print(f"  → nodo {name}: {', '.join(keys) or '-'}", flush=True)
    return on_node
