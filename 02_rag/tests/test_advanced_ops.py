from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from advanced_ops import grade, lexical_query, rewrite, verify
from fakes import FakeLlm, fake_index
from retrieval import Hit


class AdvancedOpsTests(unittest.TestCase):
    def setUp(self):
        self.hits = [Hit(fake_index().chunks[0], 1.0, "prueba")]

    def test_rewrite_preserves_original_codes_for_lexical_search(self):
        rewritten = {"consulta": "liquidación del saldo", "palabras_clave": ["saldo", "firma", "formato"]}
        llm = FakeLlm({"reescribir": [rewritten]})
        self.assertEqual(rewrite(llm, "DEM-AMZ-09"), rewritten)
        self.assertIn("DEM-AMZ-09", lexical_query("DEM-AMZ-09", rewritten))
        with self.assertRaises(ValueError):
            rewrite(FakeLlm({"reescribir": [{"consulta": True, "palabras_clave": []}]}), "x")

    def test_invalid_positions_and_boolean_indices_are_not_coerced(self):
        for chosen in ([True], [0], [2], [1, 1], "1"):
            with self.assertRaises(ValueError):
                grade(FakeLlm({"calificar": [{"relevantes": chosen}]}), "x", self.hits)
        self.assertEqual(grade(FakeLlm({"calificar": [{"relevantes": [1]}]}), "x", self.hits), self.hits)

    def test_invalid_citations_never_reach_the_model_judge(self):
        llm = FakeLlm({})
        self.assertFalse(verify(llm, "x", "Dato [99].", self.hits)["sustentada"])
        self.assertEqual(llm.calls, [])

    def test_judge_has_strict_boolean_and_consistent_problems(self):
        for verdict in ({"sustentada": "false", "problemas": []},
                        {"sustentada": True, "problemas": ["error"]},
                        {"sustentada": False, "problemas": []}):
            with self.assertRaises(ValueError):
                verify(FakeLlm({"verificar": [verdict]}), "x", "Dato [1].", self.hits)
        self.assertTrue(verify(FakeLlm({"verificar": [{"sustentada": True, "problemas": []}]}),
                               "x", "Dato [1].", self.hits)["sustentada"])


if __name__ == "__main__":
    unittest.main()
