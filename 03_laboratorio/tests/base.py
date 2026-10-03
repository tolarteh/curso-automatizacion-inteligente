"""Arranque común de las pruebas: src del laboratorio primero y módulos del tema 01 al final."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
import reuso  # noqa: E402,F401
import settings  # noqa: E402


class TempDirTest(unittest.TestCase):
    """Cada prueba trabaja en una carpeta temporal; nunca toca outputs/."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # SQLite abierto en Windows
        self.addCleanup(directory.cleanup)
        self.tmp = Path(directory.name)

    def copy_data(self, relative: str) -> Path:
        target = self.tmp / Path(relative).name
        source = settings.DATA / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy(source, target)
        return target


class Recorder:
    """Sustituto de Trace que guarda los eventos en memoria."""

    def __init__(self):
        self.events = []

    def emit(self, event, **data):
        self.events.append({"event": event, **data})

    def show(self, title, text=""):
        self.events.append({"event": "show", "title": title, "text": text})

    def end(self, **data):
        self.events.append({"event": "run_end", **data})

    def kinds(self):
        return [event["event"] for event in self.events]


class Pendiente(NotImplementedError):
    """Una prueba de aceptación detecta un TODO del reto sin resolver (no es un error del andamiaje)."""


def pendiente_si(condicion: bool, mensaje: str) -> None:
    if condicion:
        raise Pendiente(mensaje)
