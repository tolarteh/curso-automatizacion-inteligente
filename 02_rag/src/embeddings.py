"""Embeddings reales y locales, con orden, cantidad y dimensiones verificadas."""
import os

from openai import OpenAI, OpenAIError
from model_config import local_url
from trace_log import Trace
from vectors import normalize_vectors


class Embedder:
    def __init__(self, trace: Trace):
        self.base_url = local_url(os.environ.get("EMBED_BASE_URL", "http://localhost:1234/v1"))
        self.model = os.environ.get("EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")
        self.doc_prefix = os.environ.get("EMBED_DOC_PREFIX", "search_document: ")
        self.query_prefix = os.environ.get("EMBED_QUERY_PREFIX", "search_query: ")
        self.dimension = None
        self.trace = trace
        self.client = OpenAI(base_url=self.base_url, api_key="lm-studio", timeout=60.0, max_retries=0)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Los textos de embeddings no pueden estar vacíos.")
        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
        except OpenAIError as exc:
            self.trace.show("ERROR DE EMBEDDINGS", f"{type(exc).__name__}: {exc}\n"
                            "Se requiere el modelo local; no hay respaldo remoto ni reintento.")
            self.trace.end(completed=False, reason="error de embeddings")
            raise SystemExit(2) from exc
        if any(type(row.index) is not int for row in response.data):
            raise ValueError("Los índices de embeddings deben ser enteros.")
        rows = sorted(response.data, key=lambda item: item.index)
        if [row.index for row in rows] != list(range(len(texts))):
            raise ValueError("Embeddings incompletos o con índices repetidos.")
        vectors = [row.embedding for row in rows]
        matrix = normalize_vectors(vectors, len(texts))
        dimension = matrix.shape[1]
        if self.dimension is not None and self.dimension != dimension:
            raise ValueError("Cambió la dimensión del modelo de embeddings durante la ejecución.")
        self.dimension = dimension
        self.trace.emit("embedding_response", model=self.model, count=len(vectors), dimension=dimension)
        return vectors

    def embed_documents(self, texts: list[str], batch: int = 32) -> list[list[float]]:
        if (type(batch) is not int or batch < 1 or not texts
                or any(not isinstance(text, str) or not text.strip() for text in texts)):
            raise ValueError("Se necesita un lote positivo y al menos un documento.")
        vectors = []
        for start in range(0, len(texts), batch):
            vectors.extend(self._embed([self.doc_prefix + text for text in texts[start:start + batch]]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("La pregunta de búsqueda no puede estar vacía.")
        return self._embed([self.query_prefix + text])[0]
