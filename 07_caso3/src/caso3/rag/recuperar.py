"""Recuperación BM25: filtrar por fecha antes de ordenar por relevancia."""
from collections import Counter
from datetime import date
import math
import re

from caso3.herramientas.normalizar import plain
from caso3.rag.indexar import indexar


def rank(query, fragments):
    tokens = [re.findall(r"[a-z0-9]+", plain(f.texto)) for f in fragments]
    query_tokens = set(re.findall(r"[a-z0-9]+", plain(query)))
    if not tokens or not query_tokens:
        raise ValueError("Consulta vacía o sin normas vigentes.")
    average = sum(map(len, tokens)) / len(tokens)
    scores = []
    for fragment, words in zip(fragments, tokens):
        counts = Counter(words)
        score = 0.0
        for term in query_tokens:
            frequency = sum(term in doc for doc in tokens)
            idf = math.log(1 + (len(tokens) - frequency + 0.5) / (frequency + 0.5))
            tf = counts[term]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(words) / average))
        scores.append((score, fragment))
    return [f.citar() for score, f in sorted(scores, key=lambda pair: -pair[0]) if score > 0]


def norma_vigente(fecha: date, *, corpus=None):
    rules = {f.norma for f in indexar(corpus) if f.norma.vigente(fecha)}
    if len(rules) != 1:
        raise ValueError(f"Se esperaba una norma vigente única para {fecha}; hay {len(rules)}.")
    return next(iter(rules))


def recuperar_regla(consulta: str, fecha_expediente: date, *, corpus=None):
    fragments = [f for f in indexar(corpus) if f.norma.vigente(fecha_expediente)]
    return rank(consulta, fragments)


def recuperar_sin_filtro(consulta: str, *, corpus=None):
    """Contraejemplo deliberado: NO utilizar en el flujo de aprobación."""
    return rank(consulta, indexar(corpus))
