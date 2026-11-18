"""API inspirada en Graph, sin autenticación ni compatibilidad Graph real."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import closing
import json
import sqlite3
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from contracts import ControlError, ROOT, digest, read_json


def server(port=8765):
    messages = read_json(ROOT / "data" / "messages.json")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urlparse(self.path)
            if query.path != "/messages":
                self.send_error(404)
                return
            try:
                offset = int(parse_qs(query.query).get("offset", ["0"])[0])
                if offset < 0 or offset > len(messages):
                    raise ValueError()
            except ValueError:
                self.send_error(400)
                return
            page = messages[offset:offset + 2]
            next_offset = offset + len(page)
            result = {"value": page, "next_offset": next_offset if next_offset < len(messages) else None}
            payload = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def fetch_events(base_url="http://127.0.0.1:8765", max_pages=4, max_events=8):
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ControlError("La API de correo debe ser local y simulada.")
    events, offset, seen = [], 0, set()
    for _ in range(max_pages):
        if offset in seen:
            raise ControlError("Ciclo de paginación.")
        seen.add(offset)
        with urlopen(f"{base_url}/messages?offset={offset}", timeout=5) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ControlError("Página demasiado grande.")
        page = json.loads(payload)
        if not isinstance(page["value"], list):
            raise ControlError("Página inválida.")
        events.extend(page["value"])
        if len(events) > max_events:
            raise ControlError("Límite de eventos excedido.")
        offset = page["next_offset"]
        if offset is None:
            return events
        if type(offset) is not int or offset < 0:
            raise ControlError("Cursor inválido.")
    raise ControlError("Límite de páginas excedido.")


class EventLedger:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, hash TEXT)")

    def accept(self, event):
        if not isinstance(event, dict) or set(event) != {"id", "sender", "subject", "body"}:
            raise ControlError("Contrato del evento inválido.")
        if any(not isinstance(value, str) or not value.strip() for value in event.values()):
            raise ControlError("Campos vacíos o no textuales.")
        if len(event["body"]) > 8000:
            raise ControlError("Correo demasiado largo.")
        event_hash = digest(event)
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                stored = db.execute("SELECT hash FROM events WHERE id = ?", (event["id"],)).fetchone()
                if stored is not None:
                    if stored[0] != event_hash:
                        raise ControlError("ID de evento repetido con contenido distinto.")
                    return False
                db.execute("INSERT INTO events(id, hash) VALUES (?, ?)", (event["id"], event_hash))
            return True


if __name__ == "__main__":
    print("API simulada: http://127.0.0.1:8765/messages")
    server().serve_forever()
