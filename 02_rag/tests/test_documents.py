import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from documents import load_documents, load_questions, normalize, parse_document
from settings import ROLES


class DocumentTests(unittest.TestCase):
    def test_corpus_and_gold_are_consistent(self):
        docs = load_documents()
        questions = load_questions()
        self.assertEqual(len(docs), 8)
        self.assertEqual(len(questions), 15)
        self.assertEqual(sum(doc.classification == "reservada" for doc in docs), 1)
        self.assertEqual(sum(doc.origin == "externo" for doc in docs), 1)
        for question in questions:
            visible = [doc for doc in docs if doc.classification in ROLES[question["rol"]]
                       and doc.origin == "interno"]
            if question["evidencia"]:
                self.assertTrue(any(normalize(question["evidencia"]) in normalize(doc.body)
                                    for doc in visible), question["id"])
            corpus = normalize(" ".join(doc.body for doc in visible))
            for key in question["claves"]:
                self.assertTrue(any(normalize(alt) in corpus for alt in key.split("|")), question["id"])

    def test_missing_unknown_and_duplicate_metadata_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.md"
            for text in ("sin metadatos", "---\ncodigo: D-1\n---\ntexto",
                         "---\ncodigo: D-1\ncodigo: D-1\n---\ntexto",
                         "---\ncodigo: D-1\ntitulo: prueba\nclasificacion: secreta\norigen: interno\n---\ntexto"):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    parse_document(path)

    def test_empty_folder_and_duplicate_documents_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaises(ValueError):
                load_documents(folder)
            content = "---\ncodigo: D-1\ntitulo: prueba\nclasificacion: interna\norigen: interno\n---\ntexto"
            for name in ("a.md", "b.md"):
                (folder / name).write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_documents(folder)

    def test_invalid_gold_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            question = load_questions()[0]
            for value in ([], [question, question], [{**question, "rol": "desconocido"}],
                          [{**question, "evidencia": None}], [{**question, "claves": [True]}]):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_questions(path)


if __name__ == "__main__":
    unittest.main()
