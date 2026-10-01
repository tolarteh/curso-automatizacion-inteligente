from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from documents import load_questions
from evaluation import evaluate_retrieval, judge_answer, key_present, rank_metrics
from fakes import FakeEmbedder, fake_index
from retrieval import Hit, Index
from settings import NO_EVIDENCE


class EvaluationTests(unittest.TestCase):
    def test_metrics_match_hand_calculation_and_denominator(self):
        metrics = rank_metrics([1, 3, None, 5])
        self.assertEqual(metrics["hit@1"], 1 / 4)
        self.assertEqual(metrics["hit@3"], 2 / 4)
        self.assertAlmostEqual(metrics["mrr@5"], (1 + 1 / 3 + 1 / 5) / 4)
        for values in ([], [True], [0], [6]):
            with self.assertRaises(ValueError):
                rank_metrics(values)

    def test_filtered_configurations_have_zero_leaks_and_external_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            embedder = FakeEmbedder()
            fixed = Index.build(embedder, "fijo", folder=Path(directory))
            sections = fake_index()
            result = evaluate_retrieval(load_questions(), embedder, fixed, sections, Mock())
        self.assertEqual(set(result["summary"]), {"A", "B", "C", "D"})
        for name in ("B", "C", "D"):
            self.assertEqual(result["summary"][name]["fugas"], 0)
            self.assertEqual(result["summary"][name]["externos"], 0)
            self.assertEqual(len(result["positions"][name]), 13)

    def test_keyword_alternatives_and_numeric_boundaries(self):
        self.assertTrue(key_present("En tres días hábiles.", "3 dias habiles|tres dias habiles"))
        self.assertTrue(key_present("Máximo 200.000 pesos.", "200.000|200000"))
        for text in ("2000000 pesos", "1.200.000 pesos", "200.000,50 pesos"):
            self.assertFalse(key_present(text, "200.000|200000"))
        question = next(question for question in load_questions() if question["id"] == "q02")
        hits = [Hit(fake_index().chunks[0], 1.0, "prueba")]
        self.assertTrue(judge_answer(question, "La cuenta se bloquea y los repositorios se transfieren [1].",
                                     hits)[0])

    def test_judge_checks_actual_citation_bounds_and_abstention(self):
        question = load_questions()[0]
        hits = [Hit(fake_index().chunks[0], 1.0, "prueba")]
        self.assertTrue(judge_answer(question, "Máximo 0,5 % y 200.000 pesos [1].", hits)[0])
        self.assertFalse(judge_answer(question, "Máximo 0,5 % y 200.000 pesos [99].", hits)[0])
        self.assertFalse(judge_answer(question, "Máximo 0,5 % y 200.000 pesos, o 10 % [1].", hits)[0])
        self.assertFalse(judge_answer(question, None, hits)[0])
        null_question = load_questions()[11]
        self.assertTrue(judge_answer(null_question, NO_EVIDENCE, [])[0])
        self.assertFalse(judge_answer(null_question, NO_EVIDENCE + " El presupuesto es 2.", [])[0])


if __name__ == "__main__":
    unittest.main()
