import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import FakeEmbedder, FakeLlm, fake_index
from settings import NO_EVIDENCE

basic = importlib.import_module("01_rag_basico")


class BasicTests(unittest.TestCase):
    def test_context_and_citations_are_observable_without_claiming_fidelity(self):
        llm = FakeLlm({"generar_basico": ["Dato [1]."]})
        result = basic.answer("amortización", llm, FakeEmbedder(), fake_index())
        self.assertTrue(result["citas_validas"])
        self.assertIn('"fuente"', llm.calls[0]["messages"][-1]["content"])
        self.assertFalse(result["abstencion"])

    def test_invalid_citations_and_abstention_remain_explicit(self):
        for text, expected in (("Dato [99].", False), (NO_EVIDENCE, False)):
            llm = FakeLlm({"generar_basico": [text]})
            result = basic.answer("amortización", llm, FakeEmbedder(), fake_index())
            self.assertEqual(result["citas_validas"], expected)
            self.assertEqual(result["abstencion"], text == NO_EVIDENCE)

    def test_uncontrolled_pipeline_never_calls_remote_model(self):
        llm = FakeLlm({}, backend="groq")
        with self.assertRaisesRegex(ValueError, "local"):
            basic.answer("pregunta", llm, FakeEmbedder(), fake_index())
        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
