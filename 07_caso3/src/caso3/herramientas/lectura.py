"""Lectura acotada al expediente, sin OCR ni servicios implícitos."""
from datetime import date
import json
from pathlib import Path
import re

from pypdf import PdfReader

from caso3.contratos import Documento
from caso3.herramientas.normalizar import plain


class OCRRequerido(ValueError):
    pass


def confined(folder: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("La ruta debe ser relativa al expediente y no contener '..'.")
    target = (folder / raw).resolve(strict=True)
    if not target.is_relative_to(folder.resolve()):
        raise ValueError("La ruta sale del expediente.")
    return target


def leer_meta_expediente(path: Path) -> dict:
    meta = json.loads((path / "expediente.json").read_text(encoding="utf-8"))
    if set(meta) != {"id", "fecha", "documentos"} or not re.fullmatch(r"E\d{2}", meta["id"]):
        raise ValueError("Manifest de expediente inválido.")
    date.fromisoformat(meta["fecha"])
    ids = []
    routes = []
    for entry in meta["documentos"]:
        if set(entry) != {"id", "ruta"} or not re.fullmatch(r"[a-z][a-z0-9_]*", entry["id"]):
            raise ValueError("Entrada documental inválida.")
        ids.append(entry["id"])
        routes.append(confined(path, entry["ruta"]))
    if not ids or len(ids) != len(set(ids)) or len(routes) != len(set(routes)):
        raise ValueError("El manifest contiene documentos vacíos o duplicados.")
    return meta


def leer_documento(path: Path, doc_id: str | None = None, ocr: bool = False) -> Documento:
    if ocr:
        raise ValueError("OCR no configurado. No se cargan modelos ni servicios automáticamente.")
    if path.stat().st_size > 5_000_000:
        raise ValueError("El documento supera el límite de 5 MB.")
    if path.suffix.lower() == ".pdf":
        pages = PdfReader(path).pages
        if not pages or len(pages) > 30:
            raise ValueError("El PDF debe contener de 1 a 30 páginas.")
        texts = []
        for number, page in enumerate(pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise OCRRequerido(f"{path.name}, página {number}: se requiere OCR.")
            texts.append(text)
        text = "\n".join(texts)
    elif path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Formato documental no permitido: {path.suffix}")
    if not text.strip() or len(text) > 60_000:
        raise ValueError("Documento vacío o superior a 60.000 caracteres.")
    match = re.search(r"(?im)^tipo:\s*(\w+)", plain(text))
    kind = match[1] if match else "otro"
    if kind not in {"solicitud", "cotizacion", "factura", "certificado", "otro"}:
        kind = "otro"
    return Documento(id=doc_id or path.stem, tipo=kind, ruta=path.name, texto=text)


def cargar_expediente(path: Path, *, permitir_ocr_pendiente: bool = False) -> list[Documento]:
    meta = leer_meta_expediente(path)
    docs = []
    for entry in meta["documentos"]:
        try:
            doc = leer_documento(confined(path, entry["ruta"]), entry["id"])
        except OCRRequerido as exc:
            if not permitir_ocr_pendiente:
                raise
            doc = Documento(id=entry["id"], tipo="otro", ruta=entry["ruta"], texto=f"OCR_REQUERIDO: {exc}")
        docs.append(doc)
    if sum(len(d.texto) for d in docs) > 150_000:
        raise ValueError("El expediente supera el límite de contexto de 150.000 caracteres.")
    return docs
