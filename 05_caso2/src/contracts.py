"""Contratos pequeños: el contenido del correo nunca es una autorización."""
from enum import StrEnum
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("request_id", "employee_id", "username", "effective_date")
ROLES = ("manager", "security")
ALLOWLIST = {"personal@example.test"}


class Status(StrEnum):
    PENDING = "PENDIENTE_APROBACION"
    REJECTED = "RECHAZADO"
    STALE = "PLAN_INVALIDADO"
    PARTIAL = "PARCIAL"
    DONE = "COMPLETADO"


class ControlError(ValueError):
    """Fallo visible que bloquea la transición."""


def digest(value):
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(path.suffix + ".new")
    candidate.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    candidate.replace(path)
