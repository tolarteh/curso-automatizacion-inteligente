"""Normalización explícita: los valores ambiguos no se adivinan."""
from datetime import date
from decimal import Decimal
import re
import unicodedata


def plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


SMALL = dict(zip(
    "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve".split(),
    range(30),
))
SMALL.update(un=1, una=1, treinta=30, cuarenta=40, cincuenta=50, sesenta=60, setenta=70,
             ochenta=80, noventa=90, cien=100, ciento=100, doscientos=200, trescientos=300,
             cuatrocientos=400, quinientos=500, seiscientos=600, setecientos=700, ochocientos=800, novecientos=900)


def parse_monto(text: str) -> Decimal:
    value = plain(text).strip()
    value = re.sub(r"\b(cop|pesos|de|m/cte)\b", "", value).replace("$", "").strip()
    if re.fullmatch(r"\d+|\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}", value):
        return Decimal(value.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+\.\d{1,2}", value):
        return Decimal(value)
    if not value or re.search(r"\d", value):
        raise ValueError(f"Monto inválido o ambiguo: {text!r}")
    total, group, current = 0, 0, 0
    tokens = value.split()
    if tokens[0] == "y" or tokens[-1] == "y" or "y y" in value:
        raise ValueError(f"Monto en letras inválido: {text!r}")
    for token in tokens:
        if token == "y":
            continue
        if token in SMALL:
            current += SMALL[token]
        elif token == "mil":
            group += (current or 1) * 1000
            current = 0
        elif token in {"millon", "millones"}:
            total += (group + current or 1) * 1_000_000
            group, current = 0, 0
        else:
            raise ValueError(f"Monto en letras no reconocido: {text!r}")
    return Decimal(total + group + current)


def parse_fecha(text: str) -> date:
    value = plain(text).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        day, month, year = map(int, match.groups())
        return date(year, month, day)
    months = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
    match = re.fullmatch(r"(\d{1,2}) de ([a-z]+) de (\d{4})", value)
    if match and match[2] in months:
        return date(int(match[3]), months.index(match[2]) + 1, int(match[1]))
    raise ValueError(f"Fecha no reconocida: {text!r}")


def normalizar_nit(text: str) -> str:
    value = text.strip().replace(".", "").replace(" ", "")
    match = re.fullmatch(r"(\d{9})(?:-(\d))?", value)
    if not match:
        raise ValueError(f"NIT inválido: {text!r}")
    base, digit = match.groups()
    if digit is not None:
        remainder = sum(int(d) * w for d, w in zip(reversed(base), [3, 7, 13, 17, 19, 23, 29, 37, 41])) % 11
        expected = remainder if remainder < 2 else 11 - remainder
        if int(digit) != expected:
            raise ValueError("Dígito de verificación del NIT incorrecto.")
    return base
