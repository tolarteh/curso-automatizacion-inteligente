"""Paso 1 y 2: abrir el ZIP de forma segura y extraer el texto de cada soporte.

Se lee en memoria: nada se escribe en disco, así que no hay "zip slip". Se rechazan rutas
raras, extensiones no previstas y archivos demasiado grandes (zip bomb).
"""
from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

EXTENSIONES = (".txt", ".csv", ".md")
MAX_ARCHIVOS = 20
MAX_BYTES_ARCHIVO = 1_000_000
MAX_BYTES_TOTAL = 5_000_000


class ZipRechazado(ValueError):
    pass


@dataclass(frozen=True)
class Soporte:
    nombre: str
    sha256: str
    texto: str


def abrir_zip(path: Path) -> tuple[list[Soporte], list[str]]:
    """Devuelve los soportes legibles y las observaciones de lo que se omitió."""
    soportes, omitidos, total = [], [], 0
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ZipRechazado(f"ZIP_INVALIDO: {exc}") from exc
    with archive:
        entradas = [info for info in archive.infolist() if not info.is_dir()]
        if len(entradas) > MAX_ARCHIVOS:
            raise ZipRechazado(f"ZIP_RECHAZADO: más de {MAX_ARCHIVOS} archivos.")
        for info in entradas:
            ruta = PurePosixPath(info.filename.replace("\\", "/"))
            if ruta.is_absolute() or ".." in ruta.parts:
                raise ZipRechazado(f"ZIP_RECHAZADO: ruta no permitida {info.filename}")
            if ruta.suffix.lower() not in EXTENSIONES:
                omitidos.append(f"{info.filename}: extensión no prevista, no se procesa")
                continue
            if info.file_size > MAX_BYTES_ARCHIVO:
                raise ZipRechazado(f"ZIP_RECHAZADO: {info.filename} supera {MAX_BYTES_ARCHIVO} bytes.")
            total += info.file_size
            if total > MAX_BYTES_TOTAL:
                raise ZipRechazado("ZIP_RECHAZADO: el contenido descomprimido es demasiado grande.")
            data = archive.read(info)[:MAX_BYTES_ARCHIVO + 1]
            if len(data) > MAX_BYTES_ARCHIVO:
                raise ZipRechazado(f"ZIP_RECHAZADO: {info.filename} supera {MAX_BYTES_ARCHIVO} bytes.")
            soportes.append(Soporte(ruta.name, hashlib.sha256(data).hexdigest(), extraer_texto(data)))
    if not soportes:
        raise ZipRechazado("ZIP_VACIO: no hay soportes legibles.")
    return soportes, omitidos


def extraer_texto(data: bytes) -> str:
    """Texto plano. Para PDF o Word se agregaría aquí una librería (pypdf, python-docx)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")
