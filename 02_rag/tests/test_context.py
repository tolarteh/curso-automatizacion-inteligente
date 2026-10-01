import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from context import cited_numbers, format_context, is_abstention, valid_citations
from fakes import fake_index
from retrieval import Hit
from settings import NO_EVIDENCE


class ContextTests(unittest.TestCase):
    def test_sources_and_citation_positions_are_explicit(self):
        hits = [Hit(fake_index().chunks[0], 1.0, "prueba")]
        records = json.loads(format_context(hits))
        self.assertEqual(records[0]["n"], 1)
        self.assertEqual(records[0]["fuente"], hits[0].chunk.doc)
        self.assertEqual(cited_numbers("uno [1], dos [2, 3], inválida [-1]"), {1, 2, 3, -1})
        self.assertTrue(valid_citations("Dato [1].", hits))
        for text in ("sin citas", "Dato [0].", "Dato [1, 2].", "Dato [1] y [-1]."):
            self.assertFalse(valid_citations(text, hits))

    def test_abstention_cannot_hide_an_additional_answer(self):
        self.assertTrue(is_abstention(NO_EVIDENCE))
        self.assertFalse(is_abstention(NO_EVIDENCE + " Pero el dato es 10 %."))


if __name__ == "__main__":
    unittest.main()
