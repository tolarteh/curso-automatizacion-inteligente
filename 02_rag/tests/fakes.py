"""Dobles exclusivos de pruebas, nunca importados por las lecciones."""
from collections import Counter
import hashlib
import re

from chunking import chunk_by_section
from documents import load_documents, normalize
from retrieval import Index


class FakeEmbedder:
    base_url = "http://localhost:1234/v1"
    model = "doble-de-prueba"
    doc_prefix = "search_document: "
    query_prefix = "search_query: "

    def __init__(self):
        self.calls = []

    def embed_query(self, text):
        counts = Counter(re.findall(r"[a-z0-9]+", normalize(text)))
        vector = [0.0] * 64
        for token, count in counts.items():
            bucket = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % 64
            vector[bucket] += count
        return vector

    def embed_documents(self, texts):
        self.calls.append(texts)
        return [self.embed_query(text) for text in texts]


def fake_index():
    chunks = [chunk for doc in load_documents() for chunk in chunk_by_section(doc)]
    return Index(chunks, FakeEmbedder().embed_documents([chunk.indexed_text for chunk in chunks]))
