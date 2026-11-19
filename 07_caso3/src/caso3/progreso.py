"""Progreso visible en stderr y registro en disco de las listas de write_todos."""
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time

from langchain_core.callbacks import BaseCallbackHandler

# Dentro de los argumentos JSON, el texto documental llega escapado y no coincide con este patrón.
DOC_ID = re.compile(r'"id"\s*:\s*"([^"\\]+)"')


class Progreso(BaseCallbackHandler):
    def __init__(self, total_docs: int, agente: str = "orquestador", todos_log: Path | None = None):
        self.start = time.perf_counter()
        self.total = total_docs
        self.agente = agente
        self.todos_log = todos_log
        self.runs = {}

    def log(self, text):
        print(f"[{time.perf_counter() - self.start:6.0f}s] {text}", file=sys.stderr, flush=True)

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        # Los subagentes de Deep Agents traen su nombre; el grafo raíz usa el de este registro.
        agent = (metadata or {}).get("lc_agent_name") or self.agente
        self.runs[run_id] = dict(agente=agent, args="", ids=[], inicio=time.perf_counter())
        self.log(f"{agent}: llamada al modelo")

    def on_llm_new_token(self, token, *, chunk=None, run_id, **kwargs):
        # Los tokens llegan solo con streaming, que el proveedor local activa.
        run = self.runs.get(run_id)
        if run is None or run["agente"] != "clasificador" or chunk is None:
            return
        for part in getattr(chunk.message, "tool_call_chunks", None) or []:
            run["args"] += part.get("args") or ""
        ids = DOC_ID.findall(run["args"])
        for position in range(len(run["ids"]), len(ids)):
            if position:
                self.log(f"clasificador: documento {position}/{self.total} terminado: {ids[position - 1]}")
            self.log(f"clasificador: emitiendo documento {position + 1}/{self.total}: {ids[position]}")
        run["ids"] = ids

    def on_llm_end(self, response, *, run_id, **kwargs):
        run = self.runs.pop(run_id, None)
        if run is None:
            return
        if run["ids"]:
            self.log(f"clasificador: documento {len(run['ids'])}/{self.total} terminado: {run['ids'][-1]}")
        message = getattr(response.generations[0][0], "message", None) if response.generations else None
        calls = getattr(message, "tool_calls", None) or []
        usage = getattr(message, "usage_metadata", None) or {}
        self.log(f"{run['agente']}: respuesta en {time.perf_counter() - run['inicio']:.0f} s, "
                 f"{usage.get('output_tokens', '?')} tokens de salida -> "
                 f"{', '.join(c['name'] for c in calls) or 'sin herramienta'}")
        for call in calls:
            if call["name"] == "write_todos" and self.todos_log:
                # Se registra lo que pidió el modelo, aunque un control luego deniegue la herramienta.
                self.todos_log.parent.mkdir(parents=True, exist_ok=True)
                with self.todos_log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(dict(hora=datetime.now().isoformat(timespec="seconds"),
                                                 agente=run["agente"], todos=call["args"].get("todos")),
                                            ensure_ascii=False) + "\n")

    def on_llm_error(self, error, *, run_id, **kwargs):
        run = self.runs.pop(run_id, None)
        self.log(f"{run['agente'] if run else 'agente'}: error del modelo: {type(error).__name__}: {error}")
