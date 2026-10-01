import json
import re

from settings import EXPECTED, PROMPTS


def read_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8").strip()


def parse_json(text: str | None):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("El modelo no devolvió texto JSON.")
    fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.DOTALL)
    return json.loads(fenced.group(1) if fenced else text)


def extract_sql(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("El modelo no devolvió una consulta.")
    fenced = re.fullmatch(r"\s*```(?:sql|sqlite)?\s*(.*?)\s*```\s*", text, re.DOTALL)
    return (fenced.group(1) if fenced else text).strip().rstrip(";")


def expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def evaluate_rows(rows: list[dict]) -> tuple[bool, str]:
    counts = {}
    for row in rows:
        if set(row) != {"region", "retrasados"}:
            return False, "Se necesitan exactamente las columnas region y retrasados."
        region, count = row["region"], row["retrasados"]
        if not isinstance(region, str) or type(count) is not int or region in counts:
            return False, "Tipos incorrectos o región duplicada."
        counts[region] = count
    reference = {row["region"]: row["retrasados"] for row in expected()["por_region"]}
    if counts != reference:
        return False, f"Conteos obtenidos: {counts}. Referencia: {reference}."
    return True, "Coincide con los cuatro conteos de referencia, sin evaluación de un modelo."


def json_format(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
