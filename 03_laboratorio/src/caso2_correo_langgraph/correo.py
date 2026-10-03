"""El correo como dato y la fuente de correo intercambiable (MailSource).

El grafo no sabe de dónde viene un correo: recibe un `Correo`. En el laboratorio se usa
MockMailbox (una carpeta de .json y .eml). Un buzón real (por ejemplo, una API de correo
consultada cada N segundos o un webhook) solo tendría que cumplir MailSource; el grafo no cambia.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Protocol

MAX_CUERPO = 8_000  # caracteres: un correo más largo se recorta antes de llegar al modelo


@dataclass(frozen=True)
class Correo:
    id: str
    remitente: str      # solo la dirección, en minúsculas
    nombre_remitente: str
    asunto: str
    cuerpo: str
    recibido: str       # ISO 8601

    def to_dict(self) -> dict:
        return asdict(self)

    def texto(self) -> str:
        return f"Asunto: {self.asunto}\n\n{self.cuerpo}"


def nuevo_correo(id: str, de: str, asunto: str, cuerpo: str, recibido: str) -> Correo:
    nombre, direccion = parseaddr(de or "")
    return Correo(id=str(id), remitente=direccion.strip().lower(), nombre_remitente=nombre.strip(),
                  asunto=(asunto or "").strip(), cuerpo=(cuerpo or "").strip()[:MAX_CUERPO],
                  recibido=recibido or "")


class MailSource(Protocol):
    """Cualquier fuente que entregue los correos nuevos desde la última consulta."""

    def nuevos(self) -> list[Correo]:
        ...


def leer_json(path: Path) -> Correo:
    data = json.loads(path.read_text(encoding="utf-8"))
    return nuevo_correo(data.get("id") or path.stem, data.get("de", ""), data.get("asunto", ""),
                        data.get("cuerpo", ""), data.get("recibido", ""))


def leer_eml(path: Path) -> Correo:
    with path.open("rb") as stream:
        message = BytesParser(policy=policy.default).parse(stream)
    body = message.get_body(preferencelist=("plain",))
    content = body.get_content() if body is not None else ""
    try:
        received = parsedate_to_datetime(message["Date"]).isoformat() if message["Date"] else ""
    except (TypeError, ValueError):
        received = ""
    return nuevo_correo(path.stem, str(message["From"] or ""), str(message["Subject"] or ""),
                        content, received)


class MockMailbox:
    """Buzón simulado: una carpeta con correos sintéticos en .json o .eml.

    Devuelve cada archivo una sola vez por instancia. Entre ejecuciones, el programa evita
    reprocesar con el checkpointer (un hilo por correo).
    """

    def __init__(self, carpeta: Path, solo: str | None = None):
        self.carpeta = Path(carpeta)
        self.solo = solo
        self.entregados: set[str] = set()

    def nuevos(self) -> list[Correo]:
        if not self.carpeta.is_dir():
            raise FileNotFoundError(f"No existe el buzón simulado: {self.carpeta}")
        correos = []
        for path in sorted(self.carpeta.iterdir()):
            if path.suffix.lower() not in (".json", ".eml") or path.stem in self.entregados:
                continue
            if self.solo and path.stem != self.solo:
                continue
            correos.append(leer_json(path) if path.suffix.lower() == ".json" else leer_eml(path))
            self.entregados.add(path.stem)
        if self.solo and not correos and self.solo not in self.entregados:
            raise FileNotFoundError(f"No hay un correo llamado {self.solo} en {self.carpeta}")
        return correos
