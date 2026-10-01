import json
import re

from documents import normalize
from retrieval import Hit
from settings import NO_EVIDENCE


def format_context(hits: list[Hit]) -> str:
    return json.dumps([{"n": n, "fuente": hit.chunk.doc, "seccion": hit.chunk.section,
                        "clasificacion": hit.chunk.classification, "texto": hit.chunk.text}
                       for n, hit in enumerate(hits, 1)], ensure_ascii=False)


def cited_numbers(answer: str) -> set[int]:
    groups = re.findall(r"\[\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*\]", answer)
    return {int(number) for group in groups for number in re.split(r"\s*,\s*", group)}


def is_abstention(answer: str) -> bool:
    return normalize(answer.rstrip(" .")) == normalize(NO_EVIDENCE.rstrip(" ."))


def valid_citations(answer: str, hits: list[Hit]) -> bool:
    cited = cited_numbers(answer)
    return bool(cited) and all(1 <= n <= len(hits) for n in cited)
