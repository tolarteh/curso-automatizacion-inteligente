"""Las métricas no confunden una corrida buena con consistencia."""
from datetime import date
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from langfuse import Evaluation

from caso3.contratos import Clasificacion, Dictamen, Traza
from caso3.evals.langfuse import _evaluator, publish_experiment, require_credentials, verify_trace
from caso3.evals.metricas import pass_hat_k, score_classifier, score_verifier
from caso3.evals.run_evals import build_context, gold_rules, load_golden, main, run_evals, summarize


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

    def test_langfuse_trace_contains_only_synthetic_ids_and_metrics(self):
        case = next(row for row in load_golden() if row["id"] == "E05")

        class FakeSpan:
            def update(self, **kwargs):
                self.output = kwargs

        class FakeContext:
            def __enter__(self):
                return span

            def __exit__(self, *args):
                return False

        class FakeClient:
            def start_as_current_observation(self, **kwargs):
                self.input = kwargs
                return FakeContext()

            def get_current_trace_id(self):
                return "trace-id"

        span = FakeSpan()
        client = FakeClient()
        result = SimpleNamespace(
            dictamen=SimpleNamespace(decision="devolver", hallazgos=[
                SimpleNamespace(codigo="MONTO_LETRAS"), SimpleNamespace(codigo="IVA_AMBIGUO")]),
            interrumpido=True, tokens=10, traza=Traza(expediente_id="E05", pasos=[], vueltas=0))
        with tempfile.TemporaryDirectory() as tmp:
            rows, _ = run_evals("e2e", 1, "modelo/prueba", [case], lambda *args: result,
                                Path(tmp), trace_client=client)

        self.assertEqual(rows[0]["langfuse_trace_id"], "trace-id")
        self.assertEqual(summarize(rows, 1)["corridas"], 1)
        self.assertEqual(client.input["input"], {
            "expediente": "E05", "intento": 1, "agente": "e2e", "modelo": "modelo/prueba"})
        self.assertEqual(span.output["output"]["metricas"]["decision_correcta"], 1.0)
        self.assertNotIn("documentos", repr(client.input))
        self.assertNotIn("MONTO_LETRAS", repr(span.output))

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

    def test_langfuse_requires_keys_before_evaluation(self):
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY"):
                require_credentials()

    def test_langfuse_e2e_distinguishes_valid_contract_from_altered_evidence(self):
        from test_orquestador import ScriptedModel, script

        case = next(c for c in load_golden() if c["id"] == "E03")
        for altered in (True, False):
            with self.subTest(alterado=altered), tempfile.TemporaryDirectory() as tmp:
                responses = script(case)
                if altered:
                    responses[2].tool_calls[0]["args"]["documentos"][0]["texto"] += "TEXTO_NO_EXPORTABLE"
                client = MagicMock()
                client.get_current_trace_id.return_value = "traza-prueba"
                parent = client.start_as_current_observation.return_value.__enter__.return_value
                with patch("caso3.agentes.orquestador.create_model", return_value=ScriptedModel(responses=responses)), \
                     patch("caso3.agentes.orquestador.OUTPUTS", Path(tmp)):
                    rows, _ = run_evals("e2e", 1, "modelo-prueba", [case], out_dir=tmp, trace_client=client)
                self.assertEqual(rows[0]["exito"], not altered)
                children = parent.start_observation.call_args_list
                self.assertEqual(len(children), 1 if altered else 5)
                self.assertEqual(children[0].kwargs, {"name": "07_caso3.clasificador", "as_type": "agent"})
                first = parent.start_observation.return_value.update.call_args_list[0].kwargs
                self.assertEqual(first["output"], dict(contrato_valido=True, evidencia_fiel=not altered,
                                                       control_superado=not altered))
                self.assertEqual(first["level"], "ERROR" if altered else "DEFAULT")
                self.assertEqual(parent.start_observation.return_value.end.call_count, len(children))
                self.assertNotIn("TEXTO_NO_EXPORTABLE", repr(client.mock_calls))
                self.assertNotIn("Clasificación no fiel", repr(client.mock_calls))

    def test_langfuse_requires_cloud_confirmation_for_trace(self):
        class FakeObservations:
            def __init__(self, data):
                self.data = data

            def get_many(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(data=self.data)

        observations = FakeObservations([object()])
        client = SimpleNamespace(api=SimpleNamespace(observations=observations))
        verify_trace(client, "trace-id")
        self.assertEqual(observations.kwargs, {"trace_id": "trace-id", "limit": 1})

        client.api.observations = FakeObservations([])
        with patch("caso3.evals.langfuse.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "no confirmó la recepción"):
                verify_trace(client, "trace-id")
            self.assertEqual(sleep.call_count, 5)

        client.api.observations = MagicMock()
        client.api.observations.get_many.side_effect = [SimpleNamespace(data=[]), SimpleNamespace(data=[object()])]
        with patch("caso3.evals.langfuse.time.sleep") as sleep:
            verify_trace(client, "trace-id")
            sleep.assert_called_once_with(1)

    def test_langfuse_sends_numeric_metrics_without_errors_or_documents(self):
        class FakeClient:
            def run_experiment(self, **kwargs):
                self.kwargs = kwargs

            def flush(self):
                self.flushed = True

        client = FakeClient()
        module = SimpleNamespace(Evaluation=Evaluation, get_client=lambda: client)
        row = dict(id="E01", rep=1, agente="e2e", modelo="test", exito=True,
                   error="No enviar este error", decision_correcta=1.0, tokens=4,
                   langfuse_trace_id="trace-id")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-test", "LANGFUSE_SECRET_KEY": "sk-test"}), \
             patch.dict(sys.modules, {"langfuse": module}):
            publish_experiment([row], "e2e", "test", 1, Path(tmp) / "eval.csv")

        item = client.kwargs["data"][0]
        self.assertEqual(item["input"]["metricas"], {"decision_correcta": 1.0, "exito": True, "tokens": 4})
        self.assertNotIn("error", item["input"])
        self.assertNotIn("langfuse_trace_id", item["input"])
        self.assertNotIn("No enviar este error", repr(item))
        output = client.kwargs["task"](item=item)
        scores = [evaluate(output=output) for evaluate in client.kwargs["evaluators"]]
        self.assertEqual({score.name: score.value for score in scores},
                         {"decision_correcta": 1.0, "exito": 1.0, "tokens": 4.0})
        self.assertEqual(_evaluator("decision_correcta", Evaluation)(output={}), [])
        self.assertTrue(client.flushed)

    def test_cli_can_limit_an_experiment_to_one_case(self):
        cases = load_golden()[:2]
        row = dict(id=cases[0]["id"], rep=1, agente="e2e", modelo="test", exito=True,
                   error="", falso_avance=None, vueltas=0, latencia_ms=1.0, tokens=None,
                   decision_correcta=1.0)
        with patch("caso3.evals.run_evals.load_golden", return_value=cases), \
             patch("caso3.evals.run_evals.run_evals", return_value=([row], Path("eval.csv"))) as run:
            main(["-k", "1", "--caso", cases[0]["id"]])

        self.assertEqual(run.call_args.args[3], [cases[0]])

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
