"""Genera pedidos sintéticos y calcula una referencia sin SQL ni modelo."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from settings import CUTOFF, DATABASE, PERIOD_END, PERIOD_START

MARKER = "PATRONES_SYNTHETIC_ONLY"
REGIONS = [(1, "Antioquia"), (2, "Cundinamarca"), (3, "Valle del Cauca"),
           (4, "Atlántico"), (5, "Santander")]

# Las fechas prometidas, no las entregadas, definen el periodo del informe.
ORDERS = [
    ("P-1001", 1, "2026-02-20 08:00", "2026-03-04 10:00", "2026-03-06 09:00", "entregado", 1_250_000),
    ("P-1002", 1, "2026-03-01 09:30", "2026-03-10 12:00", "2026-03-12 16:00", "entregado", 830_000),
    ("P-1003", 1, "2026-03-10 11:00", "2026-03-20 09:00", "2026-03-23 11:00", "entregado", 2_100_000),
    ("P-1004", 1, "2026-03-05 10:00", "2026-03-15 10:00", "2026-03-14 17:00", "entregado", 640_000),
    ("P-1005", 1, "2026-03-15 14:00", "2026-03-25 10:00", "2026-03-25 08:00", "entregado", 1_780_000),
    ("P-1006", 1, "2026-02-10 08:00", "2026-02-25 10:00", "2026-03-03 15:00", "entregado", 910_000),
    ("P-1007", 1, "2026-02-12 09:00", "2026-02-27 10:00", "2026-03-05 12:00", "entregado", 450_000),
    ("P-2001", 2, "2026-02-25 10:00", "2026-03-05 10:00", "2026-03-09 14:00", "entregado", 3_200_000),
    ("P-2002", 2, "2026-03-08 09:00", "2026-03-18 10:00", None, "en_transito", 1_540_000),
    ("P-2003", 2, "2026-03-12 13:00", "2026-03-22 10:00", None, "en_transito", 780_000),
    ("P-2004", 2, "2026-03-18 15:00", "2026-03-28 10:00", None, "en_transito", 2_950_000),
    ("P-2005", 2, "2026-03-21 08:00", "2026-03-31 15:00", "2026-04-02 10:00", "entregado", 1_120_000),
    ("P-2006", 2, "2026-03-02 10:00", "2026-03-12 10:00", "2026-03-11 09:00", "entregado", 560_000),
    ("P-2007", 2, "2026-03-25 10:00", "2026-04-03 10:00", None, "en_transito", 990_000),
    ("P-3001", 3, "2026-02-28 10:00", "2026-03-08 10:00", "2026-03-10 11:00", "entregado", 1_430_000),
    ("P-3002", 3, "2026-03-09 10:00", "2026-03-19 10:00", "2026-03-21 16:00", "entregado", 2_680_000),
    ("P-3003", 3, "2026-02-20 10:00", "2026-03-02 10:00", "2026-03-01 18:00", "entregado", 720_000),
    ("P-3004", 3, "2026-03-16 10:00", "2026-03-26 10:00", "2026-03-26 10:00", "entregado", 1_050_000),
    ("P-4001", 4, "2026-03-04 10:00", "2026-03-14 10:00", "2026-03-17 12:00", "entregado", 1_870_000),
    ("P-4002", 4, "2026-02-24 10:00", "2026-03-06 10:00", "2026-03-05 15:00", "entregado", 610_000),
    ("P-4003", 4, "2026-03-19 10:00", "2026-03-29 10:00", "2026-03-28 11:00", "entregado", 1_340_000),
    ("P-5001", 5, "2026-02-27 10:00", "2026-03-07 10:00", None, "cancelado", 2_400_000),
    ("P-5002", 5, "2026-03-06 10:00", "2026-03-16 10:00", None, "cancelado", 890_000),
    ("P-5003", 5, "2026-03-14 10:00", "2026-03-24 10:00", None, "cancelado", 1_660_000),
    ("P-5004", 5, "2026-03-01 10:00", "2026-03-11 10:00", "2026-03-10 13:00", "entregado", 740_000),
    ("P-5005", 5, "2026-03-20 10:00", "2026-03-30 10:00", "2026-03-30 09:00", "entregado", 1_210_000),
]


def is_late(promised: str, delivered: str | None, status: str) -> bool:
    if status == "cancelado" or not PERIOD_START <= promised < PERIOD_END:
        return False
    return promised < CUTOFF if delivered is None else delivered > promised


def expected_result() -> dict:
    names = dict(REGIONS)
    late = [order for order in ORDERS if is_late(order[3], order[4], order[5])]
    counts: dict[str, int] = {}
    for order in late:
        region = names[order[1]]
        counts[region] = counts.get(region, 0) + 1
    rows = [{"region": name, "retrasados": count} for name, count in counts.items()]
    return {"total_retrasados": len(late),
            "por_region": sorted(rows, key=lambda row: (-row["retrasados"], row["region"])),
            "order_ids": sorted(order[0] for order in late)}


def seed_database(path: Path = DATABASE, reset: bool = False) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not reset:
            raise FileExistsError("La base ya existe. Usa --reset solo para regenerar datos sintéticos.")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as check:
            try:
                marker = check.execute("SELECT name FROM demo_metadata").fetchone()
            except sqlite3.OperationalError as exc:
                raise ValueError("La base no está identificada como sintética.") from exc
        if marker != (MARKER,):
            raise ValueError("No se reemplaza una base ajena al ejemplo.")
    temporary = path.with_name(f"{path.stem}_{uuid4().hex}.tmp")
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript("""
                CREATE TABLE demo_metadata (name TEXT NOT NULL);
                CREATE TABLE regions (region_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE orders (
                    order_id TEXT PRIMARY KEY, region_id INTEGER NOT NULL REFERENCES regions,
                    created_at TEXT NOT NULL, promised_at TEXT NOT NULL, delivered_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('entregado', 'en_transito', 'cancelado')),
                    amount_cop INTEGER NOT NULL
                );
            """)
            db.execute("INSERT INTO demo_metadata VALUES (?)", (MARKER,))
            db.executemany("INSERT INTO regions VALUES (?, ?)", REGIONS)
            db.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", ORDERS)
            db.commit()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    try:
        seed_database(reset=args.reset)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(f"Base sintética: {DATABASE}")
    print(f"Referencia sin modelo: {expected_result()}")


if __name__ == "__main__":
    main()
