from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from documents import load_documents
from fakes import FakeEmbedder, fake_index
from retrieval import Index, dense_search


class RetrievalTests(unittest.TestCase):
    def test_cache_reuses_vectors_and_tracks_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            embedder = FakeEmbedder()
            docs = load_documents()
            Index.build(embedder, docs=docs, folder=folder)
            Index.build(embedder, docs=docs, folder=folder)
            self.assertEqual(len(embedder.calls), 1)
            embedder.doc_prefix = "otro: "
            Index.build(embedder, docs=docs, folder=folder)
            self.assertEqual(len(embedder.calls), 2)
            Index.build(embedder, docs=docs, folder=folder, force=True)
            self.assertEqual(len(embedder.calls), 3)
            changed = [replace(docs[0], digest="digest-distinto"), *docs[1:]]
            Index.build(embedder, docs=changed, folder=folder)
            self.assertEqual(len(embedder.calls), 4)
            self.assertFalse(list(folder.glob("*.tmp")))

    def test_corrupt_cache_fails_instead_of_silently_rebuilding(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            embedder = FakeEmbedder()
            Index.build(embedder, folder=folder)
            path = next(folder.glob("*.json"))
            data = json.loads(path.read_text())
            data["vectors"] = [[0.0]]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                Index.build(embedder, folder=folder)
            self.assertEqual(len(embedder.calls), 1)
            Index.build(embedder, folder=folder, force=True)
            self.assertEqual(len(embedder.calls), 2)

    def test_permissions_apply_before_scoring_and_dimensions_are_checked(self):
        index = fake_index()
        vector = FakeEmbedder().embed_query("sim-procesos-core custodia")
        for role, remote in (("analista", False), ("seguridad", True)):
            hits = dense_search(index, vector, 20, role=role, remote=remote)
            self.assertTrue(all(hit.chunk.classification != "reservada" for hit in hits))
            self.assertTrue(all(not hit.chunk.quarantined for hit in hits))
        self.assertTrue(any(hit.chunk.classification == "reservada"
                            for hit in dense_search(index, vector, 20, role="seguridad")))
        self.assertTrue(any(hit.chunk.quarantined for hit in dense_search(index, vector, 20, role=None)))
        with self.assertRaises(ValueError):
            dense_search(index, [1.0])
        with self.assertRaises(ValueError):
            dense_search(index, vector, role=None, remote=True)


if __name__ == "__main__":
    unittest.main()
