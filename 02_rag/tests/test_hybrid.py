from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import FakeEmbedder, fake_index
from hybrid import hybrid_search, lexical_search, reciprocal_rank_fusion, tokenize
from retrieval import Hit


class HybridTests(unittest.TestCase):
    def test_exact_codes_are_preserved_and_catalog_is_first(self):
        self.assertIn("dem-amz-09", tokenize("¿Quién firma DEM-AMZ-09?"))
        hits = lexical_search(fake_index(), "¿Quién firma DEM-AMZ-09?", 3)
        self.assertEqual(hits[0].chunk.section, "DEM-AMZ-09")

    def test_rank_fusion_rewards_agreement_not_score_magnitude(self):
        chunks = fake_index().chunks[:3]
        a, b, c = [Hit(chunk, score, "prueba") for chunk, score in zip(chunks, [999.0, 0.01, 300.0])]
        hits = reciprocal_rank_fusion({"denso": [a, b], "bm25": [c, b]})
        self.assertEqual(hits[0].chunk.id, b.chunk.id)
        self.assertEqual(hits[0].ranks, {"denso": 2, "bm25": 2})
        self.assertAlmostEqual(hits[0].score, 2 / 62)
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({"denso": [a, a]})

    def test_hybrid_and_lexical_filter_reserved_and_quarantined_before_ranking(self):
        index = fake_index()
        query = "custodia sim-procesos-core ignora instrucciones amortizaciones"
        for hits in (lexical_search(index, query, 20),
                     hybrid_search(index, FakeEmbedder(), query, query, 20)):
            self.assertTrue(hits)
            self.assertTrue(all(hit.chunk.classification != "reservada" for hit in hits))
            self.assertTrue(all(not hit.chunk.quarantined for hit in hits))
        hits = lexical_search(index, "telemetria-sensores", 1, role="seguridad")
        self.assertEqual(hits[0].chunk.doc, "AC-SEG-2026-08")
        self.assertTrue(all(hit.chunk.doc != "AC-SEG-2026-08" for hit in
                            lexical_search(index, "telemetria-sensores", 5, role="seguridad", remote=True)))


if __name__ == "__main__":
    unittest.main()
