"""Fragmentos con procedencia y marca de cuarentena heredada del documento."""
from dataclasses import dataclass
import re

from documents import Document

PATTERNS = (
    r"ignora\w*\s+(?:\w+\s+){0,3}instrucciones",
    r"instrucci[oó]n(?:es)?\s+para\s+el\s+asistente",
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior)\s+instructions",
    r"olvida\w*\s+(?:\w+\s+){0,3}(?:reglas|instrucciones)",
    r"system\s+prompt",
)


def detect_injection(text: str) -> str | None:
    for pattern in PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match[0]
    return None


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    title: str
    section: str
    classification: str
    origin: str
    text: str
    header: str
    quarantined: str | None

    @property
    def indexed_text(self) -> str:
        return f"{self.header}\n{self.text}"


def windows(text: str, size: int, overlap: int) -> list[str]:
    if type(size) is not int or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("La ventana debe ser positiva y el solape menor que su tamaño.")
    pieces = []
    for start in range(0, len(text), size - overlap):
        pieces.append(text[start:start + size])
        if start + size >= len(text):
            break
    return pieces


def make_chunk(doc: Document, suffix: str, section: str, text: str) -> Chunk:
    return Chunk(f"{doc.code}#{suffix}", doc.code, doc.title, section, doc.classification,
                 doc.origin, text, f"{doc.title} ({doc.code}) > {section}", detect_injection(doc.body))


def chunk_fixed(doc: Document, size: int = 400, overlap: int = 80) -> list[Chunk]:
    text = re.sub(r"\s+", " ", re.sub(r"^#+\s*", "", doc.body, flags=re.MULTILINE)).strip()
    return [make_chunk(doc, f"v{n}", f"ventana {n}", piece)
            for n, piece in enumerate(windows(text, size, overlap), 1)]


def chunk_by_section(doc: Document, max_chars: int = 900) -> list[Chunk]:
    parts = re.split(r"^##\s+(.+)$", doc.body, flags=re.MULTILINE)
    sections = [("introducción", parts[0].strip())] if parts[0].strip() else []
    sections += [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]
    chunks = []
    for section_number, (name, body) in enumerate(sections, 1):
        for piece_number, piece in enumerate(windows(body, max_chars, 0), 1):
            if piece.strip():
                chunks.append(make_chunk(doc, f"s{section_number}.{piece_number}", name, piece.strip()))
    if not chunks:
        raise ValueError(f"{doc.code}: no se produjeron fragmentos.")
    return chunks


CHUNKERS = {"fijo": chunk_fixed, "secciones": chunk_by_section}
