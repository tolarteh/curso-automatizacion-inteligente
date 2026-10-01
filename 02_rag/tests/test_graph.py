import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import FakeEmbedder, FakeLlm, fake_index
from rag_graph import MAX_GENERATIONS, MAX_SEARCHES, build_graph, run
from settings import NO_EVIDENCE

REWRITE = {"consulta": "formato DEM-AMZ-09 firma", "palabras_clave": ["formato", "DEM-AMZ-09", "firma"]}
GOOD = {"sustentada": True, "problemas": []}
BAD = {"sustentada": False, "problemas": ["Afirmación sin sustento."]}


def model(*, chosen=None, answers=None, verdicts=None, backend="local"):
    return FakeLlm({"reescribir": [REWRITE] * MAX_SEARCHES,
                    "calificar": [{"relevantes": [1] if chosen is None else chosen}] * MAX_SEARCHES,
                    "generar": ["Lo firma el ordenador del gasto [1]."] * MAX_GENERATIONS
                    if answers is None else answers,
                    "verificar": [GOOD] * MAX_GENERATIONS if verdicts is None else verdicts}, backend=backend)


class GraphTests(unittest.TestCase):
    def execute(self, llm, question="¿Quién firma DEM-AMZ-09?", role="analista"):
        return run(question, role, llm, FakeEmbedder(), fake_index(), Mock())

    def test_happy_path_has_explicit_nodes_and_counters(self):
        final = self.execute(model())
        self.assertEqual(final["path"], ["reescribir", "recuperar", "calificar", "generar", "verificar"])
        self.assertEqual(final["status"], "verificada")
        self.assertEqual((final["searches"], final["generations"]), (1, 1))

    def test_no_evidence_retries_search_then_abstains_without_generation(self):
        llm = model(chosen=[])
        final = self.execute(llm, "¿Cuál es el presupuesto de Aurora para 2027?")
        self.assertEqual(final["answer"], NO_EVIDENCE)
        self.assertEqual(final["status"], "sin_evidencia")
        self.assertEqual(final["searches"], MAX_SEARCHES)
        self.assertFalse(any(call["purpose"] == "generar" for call in llm.calls))

    def test_unverified_text_is_withheld_after_generation_limit(self):
        llm = model(verdicts=[BAD] * MAX_GENERATIONS)
        final = self.execute(llm)
        self.assertEqual(final["status"], "bloqueada")
        self.assertIsNone(final["answer"])
        self.assertEqual(final["generations"], MAX_GENERATIONS)
        corrections = [call for call in llm.calls if call["purpose"] == "generar"][-1]
        self.assertIn("Afirmación sin sustento", corrections["messages"][-1]["content"])

    def test_invalid_citations_skip_judge_and_eventually_block(self):
        llm = model(answers=["Dato [99]."] * MAX_GENERATIONS)
        self.assertEqual(self.execute(llm)["status"], "bloqueada")
        self.assertFalse(any(call["purpose"] == "verificar" for call in llm.calls))

    def test_role_quarantine_and_remote_boundary_hold_in_every_model_call(self):
        for role, backend, reserved_allowed in (("analista", "local", False),
                                                ("seguridad", "groq", False),
                                                ("seguridad", "local", True)):
            llm = model(backend=backend)
            self.execute(llm, "¿Qué repositorios tienen custodia especial?", role)
            prompts = json.dumps(llm.calls, ensure_ascii=False)
            self.assertEqual("telemetria-sensores" in prompts, reserved_allowed)
            self.assertNotIn("INSTRUCCIÓN PARA EL ASISTENTE", prompts)

    def test_external_tracing_is_rejected_and_graph_draw_needs_no_model(self):
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true"}):
            with self.assertRaisesRegex(ValueError, "locales"):
                build_graph(None, None, None, None)
        drawing = build_graph(None, None, None, None).get_graph().draw_mermaid()
        for name in ("reescribir", "recuperar", "calificar", "generar", "verificar", "abstenerse", "bloquear"):
            self.assertIn(name, drawing)


if __name__ == "__main__":
    unittest.main()
