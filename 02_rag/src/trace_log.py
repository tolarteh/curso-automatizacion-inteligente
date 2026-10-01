"""Eventos locales JSONL; nunca se envían a un servicio de telemetría."""
import json
import os
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from settings import TRACES


def redact(text: str) -> str:
    for name in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[SECRETO OCULTO]")
    return re.sub(r"(?:sk-|gsk_)[A-Za-z0-9_-]{12,}", "[SECRETO OCULTO]", text)


class Trace:
    def __init__(self, lesson: str, backend: str, model: str):
        TRACES.mkdir(parents=True, exist_ok=True)
        self.path = TRACES / f"{lesson}_{uuid4().hex}.jsonl"
        self.started = time.perf_counter()
        self.emit("run_start", lesson=lesson, backend=backend, model=model, synthetic=True)

    def emit(self, event: str, **data) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(),
                  "elapsed_ms": round((time.perf_counter() - self.started) * 1000),
                  "event": event, **data}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(redact(json.dumps(record, ensure_ascii=False)) + "\n")

    def show(self, title: str, text: str = "") -> None:
        title, text = redact(title), redact(text)
        print(f"\n[{title}]\n{text}", flush=True)
        self.emit("show", title=title, text=text)

    def end(self, **data) -> None:
        self.emit("run_end", **data)
        print(f"\nTraza: {self.path}", flush=True)
