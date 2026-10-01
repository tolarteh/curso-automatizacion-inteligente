from copy import deepcopy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from planning_contract import needs_human, validate_plan
from fakes import CORRECT_SQL

PLAN = {"objetivo": "Preparar un informe de retrasos", "pasos": [
    {"n": 1, "accion": "Consultar pedidos", "ejecutor": "software",
     "herramienta": "run_sql_readonly", "sql": CORRECT_SQL, "riesgo": "bajo"},
    {"n": 2, "accion": "Redactar resumen", "ejecutor": "llm",
     "herramienta": "ninguna", "sql": "", "riesgo": "bajo"},
    {"n": 3, "accion": "Revisar antes de compartir", "ejecutor": "humano",
     "herramienta": "ninguna", "sql": "", "riesgo": "alto"},
]}


class PlanContractTests(unittest.TestCase):
    def test_valid_plan_and_human_policy(self):
        self.assertEqual(validate_plan(PLAN), [])
        self.assertTrue(needs_human(PLAN["pasos"][-1]))
        self.assertTrue(needs_human({**PLAN["pasos"][0], "riesgo": "alto"}))
        self.assertFalse(needs_human(PLAN["pasos"][0]))

    def test_shape_order_types_and_tool_allowlist(self):
        for change in ({"n": True}, {"n": 2}, {"accion": ""}, {"sql": ""},
                       {"herramienta": "enviar"}, {"ejecutor": "llm"}, {"extra": 1}):
            plan = deepcopy(PLAN)
            plan["pasos"][0].update(change)
            with self.subTest(change=change):
                self.assertTrue(validate_plan(plan))
        for value in (None, {}, {"objetivo": "", "pasos": PLAN["pasos"]},
                      {"objetivo": "x", "pasos": []}):
            self.assertTrue(validate_plan(value))

    def test_no_plan_can_skip_terminal_human_review(self):
        plan = deepcopy(PLAN)
        plan["pasos"][-1].update(ejecutor="llm", riesgo="bajo")
        self.assertTrue(validate_plan(plan))


if __name__ == "__main__":
    unittest.main()
