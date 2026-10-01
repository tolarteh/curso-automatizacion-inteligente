"""BM25 y fusión por posiciones; sus puntajes no se comparan con el coseno."""
from collections import Counter
import math
import re

from documents import normalize
from policy import validate_k
from retrieval import Hit, Index, dense_search, visible_indices

STOPWORDS = set("a al como con cual cuando de del donde el en es esta este hay la las lo los "
                "me mi no o para por que se si su sus un una y cuanto cuantos quien".split())


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalize(text)):
        if "-" in word:
            tokens.append(word)
            tokens.extend(part for part in word.split("-") if part not in STOPWORDS)
        elif word not in STOPWORDS:
            tokens.append(word)
    return tokens


def lexical_search(index: Index, query: str, k: int = 4, *, role: str | None = "analista",
                   remote: bool = False) -> list[Hit]:
    validate_k(k)
    if not isinstance(query, str) or not query.strip():
        raise ValueError("La búsqueda léxica necesita una pregunta no vacía.")
    chunks = [index.chunks[n] for n in visible_indices(index, role, remote)]
    if not chunks:
        return []
    tokenized = [tokenize(chunk.indexed_text) for chunk in chunks]
    frequency = Counter(token for tokens in tokenized for token in set(tokens))
    average_length = sum(map(len, tokenized)) / len(chunks)
    query_tokens = tokenize(query)
    hits = []
    for chunk, tokens in zip(chunks, tokenized):
        counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            tf = counts[token]
            if tf:
                df = frequency[token]
                idf = math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5))
                denominator = tf + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
                score += idf * tf * (1.5 + 1) / denominator
        if score > 0:
            hits.append(Hit(chunk, score, "bm25"))
    return sorted(hits, key=lambda hit: -hit.score)[:k]


def reciprocal_rank_fusion(rankings: dict[str, list[Hit]], top: int = 6) -> list[Hit]:
    validate_k(top)
    fused = {}
    for source, hits in rankings.items():
        if len({hit.chunk.id for hit in hits}) != len(hits):
            raise ValueError("Una lista de recuperación contiene fragmentos repetidos.")
        for rank, hit in enumerate(hits, 1):
            if hit.chunk.id not in fused:
                fused[hit.chunk.id] = Hit(hit.chunk, 0.0, "híbrido")
            entry = fused[hit.chunk.id]
            entry.score += 1 / (60 + rank)
            entry.ranks[source] = rank
    return sorted(fused.values(), key=lambda hit: -hit.score)[:top]


def hybrid_search(index: Index, embedder, query: str, lexical: str, k: int = 6, *,
                  role: str = "analista", remote: bool = False) -> list[Hit]:
    validate_k(k)
    pool = max(8, k)
    dense = dense_search(index, embedder.embed_query(query), pool, role=role, remote=remote)
    exact = lexical_search(index, lexical, pool, role=role, remote=remote)
    return reciprocal_rank_fusion({"denso": dense, "bm25": exact}, top=k)
