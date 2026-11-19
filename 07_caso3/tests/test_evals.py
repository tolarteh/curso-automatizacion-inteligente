"""Las métricas no confunden una corrida buena con consistencia."""
from datetime import date
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from caso3.contratos import Clasificacion, Dictamen, Traza
from caso3.evals.metricas import pass_hat_k, score_classifier, score_verifier
from caso3.evals.run_evals import build_context, gold_rules, load_golden, run_evals, summarize


class EvaluationTests(unittest.TestCase):
    def test_pass_power_requires_all_and_valid_k(self):
        self.assertTrue(pass_hat_k([True] * 3, 3))
        self.assertFalse(pass_hat_k([True, False, True], 3))
        self.assertFalse(pass_hat_k([True], 3))
        for k in (0, -1, True):
            with self.assertRaises(ValueError):
                pass_hat_k([], k)

    def test_old_rule_cannot_get_validity_credit_in_2026(self):
        case = next(row for row in load_golden() if row["id"] == "E04")
        old = gold_rules(case)
        self.assertEqual(score_verifier(old, "manual-2024.md", date(2026, 1, 1))["vigencia_correcta"], 0)

    def test_inputs_do_not_leak_verifier_answer(self):
        case = load_golden()[0]
        ctx = build_context("verificador", case, [])
        self.assertNotIn("reglas", ctx)
        self.assertNotIn("decision_esperada", ctx)

    def test_errors_count_as_failures_and_traces_are_typed(self):
        case = load_golden()[0]
        attempts = 0

        def runner(agent, case, model):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise ValueError("Fallo visible de prueba")
            return SimpleNamespace(
                dictamen=Dictamen(decision="aprobar", hallazgos=[], reglas=[], vueltas=0),
                interrumpido=True, tokens=10, traza=Traza(expediente_id=case["id"], pasos=[], vueltas=0))

        with tempfile.TemporaryDirectory() as tmp:
            rows, path = run_evals("e2e", 3, "modelo/prueba", [case], runner, Path(tmp), date(2026, 1, 1))
            self.assertTrue(path.is_file())
            self.assertEqual(summarize(rows, 3)["pass^3"], 0)
            self.assertEqual(summarize(rows, 3)["errores"], 1)
            traces = list(Path(tmp).glob("trazas/*/e2e/*.json"))
            self.assertEqual(len(traces), 3)
            for trace in traces:
                Traza.model_validate(json.loads(trace.read_text(encoding="utf-8"))["traza"])

    def test_false_advance_is_counted_even_if_interrupt_missing(self):
        case = next(row for row in load_golden() if row["decision_esperada"] == "devolver")
        def runner(*args):
            return SimpleNamespace(dictamen=Dictamen(decision="aprobar", hallazgos=[], reglas=[], vueltas=0),
                                   interrumpido=False, tokens=None, traza=Traza(expediente_id=case["id"], pasos=[], vueltas=0))
        with tempfile.TemporaryDirectory() as tmp:
            rows, _ = run_evals("e2e", 1, "prueba", [case], runner, Path(tmp))
            self.assertEqual(summarize(rows, 1)["falsos_avances"], 1)
            self.assertTrue(rows[0]["error"])

    def test_unknown_false_advances_are_not_reported_as_zero(self):
        def runner(*args):
            raise ValueError("Sin dictamen")
        with tempfile.TemporaryDirectory() as tmp:
            rows, _ = run_evals("e2e", 1, "prueba", load_golden()[:1], runner, Path(tmp))
            summary = summarize(rows, 1)
            self.assertIsNone(summary["falsos_avances"])
            self.assertEqual(summary["corridas_evaluables"], 0)

    def test_k3_native_pipeline_evaluation_with_cpu_model_only(self):
        from test_orquestador import ScriptedModel, script
        from caso3.agentes.orquestador import ejecutar_expediente

        def runner(agent, case, model):
            return ejecutar_expediente(Path(case["id"]), model=ScriptedModel(responses=script(case)))

        with tempfile.TemporaryDirectory() as tmp, patch("caso3.agentes.orquestador.OUTPUTS", Path(tmp)):
            rows, path = run_evals("e2e", 3, "doble_exclusivo_cpu", load_golden(), runner, Path(tmp))
            summary = summarize(rows, 3)
            self.assertEqual(summary["corridas"], 36)
            self.assertEqual(summary["errores"], 0)
            self.assertEqual(summary["pass^3"], 1)
            self.assertEqual(summary["falsos_avances"], 0)
            self.assertEqual(len(list(Path(tmp).glob("trazas/*/e2e/*.json"))), 36)
