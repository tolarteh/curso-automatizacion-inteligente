from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from chunking import CHUNKERS, Chunk
from documents import load_documents
from policy import permitted, validate_k
from settings import INDEXES
from vectors import normalize_vectors


class Index:
    def __init__(self, chunks: list[Chunk], vectors: list[list[float]]):
        if not chunks or len({chunk.id for chunk in chunks}) != len(chunks):
            raise ValueError("Se necesitan fragmentos no vacíos con identificadores únicos.")
        self.chunks = chunks
        self.vectors = vectors
        self.matrix = normalize_vectors(vectors, len(chunks))

    @classmethod
    def build(cls, embedder, chunking: str = "secciones", *, docs=None, folder: Path = INDEXES,
              force: bool = False, trace=None):
        if chunking not in CHUNKERS:
            raise ValueError(f"Fragmentación desconocida: {chunking}")
        docs = load_documents() if docs is None else docs
        chunks = [chunk for doc in docs for chunk in CHUNKERS[chunking](doc)]
        spec = {"format": 1, "chunking": chunking, "defaults": [400, 80, 900],
                "endpoint": embedder.base_url, "model": embedder.model,
                "doc_prefix": embedder.doc_prefix, "query_prefix": embedder.query_prefix,
                "documents": [(doc.code, doc.digest) for doc in docs]}
        key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()
        path = folder / f"{chunking}_{key}.json"
        cached = path.is_file() and not force
        if cached:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"key", "vectors"} or data["key"] != key:
                raise ValueError("Caché de índice inválida. Regenerar explícitamente.")
            vectors = data["vectors"]
        else:
            vectors = embedder.embed_documents([chunk.indexed_text for chunk in chunks])
        index = cls(chunks, vectors)
        if not cached:
            folder.mkdir(parents=True, exist_ok=True)
            temporary = folder / f"{key}_{uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps({"key": key, "vectors": vectors}), encoding="utf-8")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if trace is not None:
            trace.emit("index_loaded" if cached else "index_built", key=key, chunks=len(chunks),
                       dimension=index.matrix.shape[1], model=embedder.model)
        return index


@dataclass
class Hit:
    chunk: Chunk
    score: float
    source: str
    ranks: dict[str, int] = field(default_factory=dict)

    def record(self) -> dict:
        return {"chunk": asdict(self.chunk), "score": self.score, "source": self.source, "ranks": self.ranks}


def visible_indices(index: Index, role: str | None, remote: bool) -> list[int]:
    if role is None and remote:
        raise ValueError("La recuperación sin controles solo se permite localmente.")
    return [n for n, chunk in enumerate(index.chunks)
            if role is None or permitted(chunk, role, remote=remote)]


def dense_search(index: Index, vector: list[float], k: int = 4, *,
                 role: str | None = "analista", remote: bool = False) -> list[Hit]:
    validate_k(k)
    query = normalize_vectors([vector], 1)[0]
    if len(query) != index.matrix.shape[1]:
        raise ValueError("La pregunta y el índice usan dimensiones distintas.")
    visible = visible_indices(index, role, remote)
    if not visible:
        return []
    scores = index.matrix[visible] @ query
    order = np.argsort(-scores, kind="stable")[:k]
    return [Hit(index.chunks[visible[n]], float(scores[n]), "denso") for n in order]
