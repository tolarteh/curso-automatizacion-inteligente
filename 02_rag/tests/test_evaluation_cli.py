import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import FakeEmbedder, fake_index
from documents import load_questions

evaluation = importlib.import_module("03_evaluacion")


class EvaluationCliTests(unittest.TestCase):
    def test_default_evaluation_never_creates_language_client(self):
        args = SimpleNamespace(respuestas="no", reescritura=False, sin_prefijos=False, reindexar=False)
        backend = SimpleNamespace(name="local", model="demo-local")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(evaluation, "OUTPUTS", Path(directory)), \
             patch.object(evaluation, "start", return_value=(args, backend)), \
             patch.object(evaluation, "Trace"), \
             patch.object(evaluation, "Embedder", return_value=FakeEmbedder()), \
             patch.object(evaluation.Index, "build", return_value=fake_index()), \
             patch.object(evaluation, "Llm") as llm:
            self.assertEqual(evaluation.main(), 0)
            llm.assert_not_called()
            self.assertTrue((Path(directory) / "evaluation_result.json").is_file())

    def test_answer_evaluation_keeps_failed_cases_in_the_denominator(self):
        basic = importlib.import_module("01_rag_basico")
        questions = load_questions()[:2]
        hits = []
        with patch.object(basic, "answer", side_effect=[
            {"respuesta": "sin citas ni datos", "fragmentos": hits},
            {"respuesta": "otro error", "fragmentos": hits},
        ]):
            report = evaluation.evaluate_answers(questions, "basico", None, None, None, None, Mock())
        self.assertEqual(report["basico"]["total"], 2)
        self.assertEqual(report["basico"]["ok"], 0)

    def test_failed_new_run_cannot_leave_previous_success_report(self):
        args = SimpleNamespace(respuestas="no", reescritura=False, sin_prefijos=False, reindexar=False)
        backend = SimpleNamespace(name="local", model="demo-local")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation_result.json"
            path.write_text('{"completed":true}', encoding="utf-8")
            with patch.object(evaluation, "OUTPUTS", Path(directory)), \
                 patch.object(evaluation, "start", return_value=(args, backend)), \
                 patch.object(evaluation, "Trace"), \
                 patch.object(evaluation, "Embedder", side_effect=ValueError("configuración inválida")):
                self.assertEqual(evaluation.main(), 2)
            self.assertFalse(json.loads(path.read_text(encoding="utf-8"))["completed"])


if __name__ == "__main__":
    unittest.main()
