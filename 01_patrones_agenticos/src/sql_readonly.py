"""La aplicación decide qué SQL puede ejecutarse, no el prompt."""
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from settings import CUTOFF, DATABASE

SCHEMA = {
    "regions": {"region_id": "INTEGER PRIMARY KEY", "name": "TEXT"},
    "orders": {
        "order_id": "TEXT PRIMARY KEY", "region_id": "INTEGER REFERENCES regions",
        "created_at": "TEXT YYYY-MM-DD HH:MM", "promised_at": "TEXT YYYY-MM-DD HH:MM",
        "delivered_at": "TEXT YYYY-MM-DD HH:MM o NULL",
        "status": "TEXT entregado|en_transito|cancelado", "amount_cop": "INTEGER",
    },
}
SAFE_FUNCTIONS = frozenset((
    "count", "sum", "total", "avg", "min", "max", "coalesce", "ifnull", "nullif",
    "round", "abs", "date", "datetime", "julianday", "strftime", "substr",
    "lower", "upper", "trim", "length", "like",
))
ROW_LIMIT = 25
QUERY_TIMEOUT = 1.0
MAX_SQL_LENGTH = 4_000


class QueryRejected(ValueError):
    pass


def list_tables() -> dict:
    return {"tablas": SCHEMA, "relaciones": ["orders.region_id = regions.region_id"],
            "fecha_de_corte": CUTOFF, "nota": "Datos sintéticos. Solo lectura."}


def schema_text() -> str:
    return "\n".join(f"{name}({', '.join(f'{column} {kind}' for column, kind in columns.items())})"
                     for name, columns in SCHEMA.items())


def run_sql_readonly(sql: str, database: Path = DATABASE, *,
                     row_limit: int = ROW_LIMIT, timeout: float = QUERY_TIMEOUT) -> dict:
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_LENGTH:
        raise QueryRejected("SQL_INVALIDO: consulta vacía o demasiado larga.")
    if type(row_limit) is not int or not 1 <= row_limit <= ROW_LIMIT:
        raise QueryRejected("LIMITE_INVALIDO: entre 1 y 25 filas.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= QUERY_TIMEOUT:
        raise QueryRejected("LIMITE_INVALIDO: timeout mayor que cero y máximo un segundo.")
    statement = re.sub(r"\A(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/)*", "", sql, flags=re.DOTALL)
    if not re.match(r"(SELECT|WITH)\b", statement, re.IGNORECASE):
        raise QueryRejected("SQL_DENEGADO: solo SELECT o WITH de lectura.")

    denied = []
    started = time.perf_counter()
    timed_out = False

    def authorize(action, table, column, database_name, trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        empty_column = database_name is None and not column
        if action == sqlite3.SQLITE_READ and (database_name == "main" or empty_column):
            if table in SCHEMA and (not column or column in SCHEMA[table]):
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (column or "").lower() in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        denied.append(table or column or str(action))
        return sqlite3.SQLITE_DENY

    def cancelled():
        nonlocal timed_out
        timed_out = time.perf_counter() - started > timeout
        return int(timed_out)

    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
            db.execute("PRAGMA query_only = ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_LENGTH)
            db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            db.set_authorizer(authorize)
            db.set_progress_handler(cancelled, 100)
            cursor = db.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchmany(row_limit + 1)
            return {"rows": [dict(zip(columns, row)) for row in rows[:row_limit]],
                    "truncated": len(rows) > row_limit}
    except sqlite3.Error as exc:
        if timed_out:
            raise QueryRejected("SQL_TIMEOUT: consulta cancelada.") from exc
        if denied:
            raise QueryRejected(f"SQL_DENEGADO: recurso no permitido {denied[0]}.") from exc
        raise QueryRejected(f"SQL_INVALIDO: {exc}") from exc


def safe_run(sql: str) -> dict:
    try:
        return {"ok": True, **run_sql_readonly(sql)}
    except QueryRejected as exc:
        return {"ok": False, "error": str(exc)}
