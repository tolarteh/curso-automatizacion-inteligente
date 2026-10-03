"""Genera los ZIP sintéticos del caso 3 a partir de data/caso3/fuentes (reproducible).

    python 03_laboratorio\\src\\caso3_zip_sin_framework\\datos.py

Los textos de cada soporte se pueden leer en data/caso3/fuentes; los ZIP son la entrada real.
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from settings import DATA_CASO3  # noqa: E402

FUENTES = DATA_CASO3 / "fuentes"
FECHA_FIJA = (2026, 9, 25, 8, 0, 0)  # mismas fechas internas en cada regeneración


def contenido(carpeta: Path) -> dict[str, bytes]:
    """Archivos de una solicitud, con saltos de línea LF (igual en Windows y Linux)."""
    return {path.name: path.read_bytes().replace(b"\r\n", b"\n")
            for path in sorted(carpeta.iterdir()) if path.is_file()}


def generar(destino: Path = DATA_CASO3) -> list[Path]:
    creados = []
    for carpeta in sorted(p for p in FUENTES.iterdir() if p.is_dir()):
        path = destino / f"{carpeta.name}.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in contenido(carpeta).items():
                info = zipfile.ZipInfo(name, date_time=FECHA_FIJA)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        creados.append(path)
    return creados


if __name__ == "__main__":
    for created in generar():
        print(f"Generado {created}")
