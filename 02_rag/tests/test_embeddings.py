import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from embeddings import Embedder
from openai import OpenAIError
from vectors import normalize_vectors


def output(vectors, indexes=None):
    indexes = list(range(len(vectors))) if indexes is None else indexes
    return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=v) for i, v in zip(indexes, vectors)])


class EmbeddingTests(unittest.TestCase):
    def test_prefixes_batching_and_response_order(self):
        with patch("embeddings.OpenAI") as factory:
            embedder = Embedder(Mock())
            create = factory.return_value.embeddings.create
            create.side_effect = [output([[0.0, 1.0], [1.0, 0.0]], [1, 0]), output([[1.0, 1.0]])]
            self.assertEqual(embedder.embed_documents(["a", "b", "c"], batch=2),
                             [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
            self.assertEqual(create.call_args_list[0].kwargs["input"], ["search_document: a", "search_document: b"])
            create.side_effect = None
            create.return_value = output([[1.0, 0.0]])
            embedder.embed_query("pregunta")
            self.assertEqual(create.call_args.kwargs["input"], ["search_query: pregunta"])

    def test_invalid_vectors_counts_and_dimensions_fail(self):
        for vectors in ([[0.0, 0.0]], [[float("nan"), 1.0]], [[True, 1.0]], [[1.0], [1.0, 2.0]]):
            with self.assertRaises(ValueError):
                normalize_vectors(vectors, len(vectors))
        with patch("embeddings.OpenAI") as factory:
            embedder = Embedder(Mock())
            create = factory.return_value.embeddings.create
            for result in (output([]), output([[1.0], [2.0]], [0, 0])):
                create.return_value = result
                with self.assertRaises(ValueError):
                    embedder.embed_query("pregunta")
            create.return_value = output([[1.0, 0.0]])
            embedder.embed_query("primera")
            create.return_value = output([[1.0]])
            with self.assertRaises(ValueError):
                embedder.embed_query("segunda")

    def test_remote_endpoint_is_rejected_and_api_failure_stops(self):
        with patch.dict(os.environ, {"EMBED_BASE_URL": "https://example.com/v1"}):
            with self.assertRaises(ValueError):
                Embedder(Mock())
        trace = Mock()
        with patch("embeddings.OpenAI") as factory:
            embedder = Embedder(trace)
            create = factory.return_value.embeddings.create
            create.side_effect = OpenAIError("no disponible")
            with self.assertRaises(SystemExit):
                embedder.embed_query("pregunta")
            create.assert_called_once()
            trace.end.assert_called_once_with(completed=False, reason="error de embeddings")


if __name__ == "__main__":
    unittest.main()
