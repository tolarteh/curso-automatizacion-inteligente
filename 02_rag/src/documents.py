"""Documentos sintéticos con metadatos obligatorios, sin permisos por defecto."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from settings import CORPUS, QUESTIONS, ROLES


def normalize(text: str) -> str:
    unaccented = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                         if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", unaccented).strip()


@dataclass(frozen=True)
class Document:
    code: str
    title: str
    classification: str
    origin: str
    body: str
    digest: str


def parse_document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path.name}: falta el encabezado de metadatos.")
    meta = {}
    for line in match[1].splitlines():
        if ":" not in line:
            raise ValueError(f"{path.name}: metadato sin clave y valor.")
        key, value = (part.strip() for part in line.split(":", 1))
        if not key or not value or key in meta:
            raise ValueError(f"{path.name}: metadato vacío o repetido.")
        meta[key] = value
    required = {"codigo", "titulo", "clasificacion", "origen"}
    if not required <= meta.keys():
        raise ValueError(f"{path.name}: faltan metadatos obligatorios.")
    if meta["clasificacion"] not in ROLES["seguridad"] or meta["origen"] not in ("interno", "externo"):
        raise ValueError(f"{path.name}: clasificación u origen desconocidos.")
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", meta["codigo"]):
        raise ValueError(f"{path.name}: código inválido.")
    body = text[match.end():].strip()
    if not body:
        raise ValueError(f"{path.name}: documento vacío.")
    return Document(meta["codigo"], meta["titulo"], meta["clasificacion"], meta["origen"],
                    body, hashlib.sha256(text.encode("utf-8")).hexdigest())


def load_documents(folder: Path = CORPUS) -> list[Document]:
    paths = sorted(folder.glob("*.md"))
    if not paths:
        raise ValueError(f"No hay documentos Markdown en {folder}.")
    docs = [parse_document(path) for path in paths]
    if len({doc.code for doc in docs}) != len(docs):
        raise ValueError("Hay códigos de documento repetidos.")
    return docs


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError("El conjunto de evaluación debe ser una lista no vacía.")
    ids = set()
    fields = {"id", "rol", "tipo", "pregunta", "evidencia", "claves", "prohibidas"}
    for question in questions:
        if not isinstance(question, dict) or set(question) != fields:
            raise ValueError("Pregunta de evaluación con campos inválidos.")
        if any(not isinstance(question[key], str) or not question[key].strip()
               for key in ("id", "rol", "tipo", "pregunta")):
            raise ValueError("Identificador, rol, tipo y pregunta deben ser texto.")
        if question["id"] in ids or question["rol"] not in ROLES:
            raise ValueError("Identificador repetido o rol desconocido.")
        ids.add(question["id"])
        evidence = question["evidencia"]
        if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
            raise ValueError("La evidencia debe ser texto no vacío o null.")
        for key in ("claves", "prohibidas"):
            values = question[key]
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"{key} debe contener textos no vacíos.")
        if bool(evidence) != bool(question["claves"]):
            raise ValueError("Las preguntas respondibles necesitan evidencia y claves.")
    return questions
