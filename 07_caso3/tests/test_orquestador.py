"""Deep Agents real con un modelo de herramientas falso, exclusivo de las pruebas."""
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from caso3.agentes.orquestador import decision_for, ejecutar_expediente, firmar
from caso3.config import DATA
from caso3.contratos import Clasificacion, Dictamen, Extraccion, Extracciones, Hallazgo, Hallazgos, Reglas
from caso3.agentes.subagentes import ejecutar_subagente
from caso3.herramientas.auditoria import cruzar
from caso3.herramientas.lectura import cargar_expediente
from caso3.rag.recuperar import recuperar_regla
from caso3.evals.run_evals import gold_rules


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]

    @property
    def _llm_type(self):
        return "modelo-exclusivo-pruebas"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if not self.responses:
            raise AssertionError("El agente hizo una llamada al modelo no prevista.")
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0).model_copy(deep=True))])


def call(name, args=None):
    return AIMessage(content="", tool_calls=[dict(name=name, args=args or {}, id=f"call-{name}")],
                     usage_metadata=dict(input_tokens=1, output_tokens=1, total_tokens=2))


def script(case, *, revision=False):
    docs = cargar_expediente(DATA / "expedientes" / case["id"], permitir_ocr_pendiente=True)
    when = date.fromisoformat(case["fecha"])
    exts = [Extraccion.model_validate(e) for e in case["extracciones_esperadas"]]
    rules = recuperar_regla("cotizaciones certificados firma", when)
    findings = cruzar(exts, docs, fecha_expediente=when, reglas=rules)
    outputs = dict(
        clasificador=Clasificacion(documentos=docs, faltantes=case["documentos_faltantes"]),
        extractor=Extracciones(extracciones=exts), verificador=Reglas(reglas=rules),
        auditor=Hallazgos(hallazgos=findings),
        redactor=Dictamen(decision=decision_for(findings), hallazgos=findings, reglas=rules, vueltas=0),
    )
    responses = [call("write_todos", dict(todos=[dict(content="Revisar el expediente", status="in_progress")]))]
    for role, output in outputs.items():
        responses += [call("task", dict(subagent_type=role, description="Revisar.")),
                      call(type(output).__name__, output.model_dump(mode="json"))]
    responses += [call("proponer_aprobacion")]
    return responses


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.cases = [json.loads(line) for line in (DATA / "golden.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_twelve_cases_reach_native_interrupt_without_network(self):
        with patch("socket.socket.connect", side_effect=AssertionError("Red prohibida en CPU")):
            for case in self.cases:
                with self.subTest(case=case["id"]):
                    model = ScriptedModel(responses=script(case))
                    result = ejecutar_expediente(Path(case["id"]), model=model)
                    self.assertTrue(result.interrumpido)
                    self.assertIsNone(result.firma)
                    self.assertEqual(result.dictamen.decision, case["decision_esperada"])
                    self.assertEqual({h.codigo for h in result.hallazgos}, set(case["hallazgos_esperados"]))
                    self.assertEqual(len(result.traza.pasos), 5)
                    self.assertEqual(result.tokens, 24)

    def test_human_resume_records_signature_once(self):
        model = ScriptedModel(responses=script(self.cases[0]) + [AIMessage(content="Propuesta firmada.")])
        result = ejecutar_expediente(Path("E01"), model=model)
        with self.assertRaises(ValueError):
            firmar(result, "", True)
        with self.assertRaisesRegex(ValueError, "rol"):
            firmar(result, "Revisor sintético", True, "responsable de compras")
        signature = firmar(result, "Revisor sintético", True, "dirección")
        self.assertEqual(signature["hash"], result.hash)
        self.assertEqual(signature["decision"], "aceptada")
        with self.assertRaises(ValueError):
            firmar(result, "Otro revisor", True)

    def test_reject_does_not_resume_or_approve(self):
        model = ScriptedModel(responses=script(self.cases[0]))
        result = ejecutar_expediente(Path("E01"), model=model)
        self.assertEqual(firmar(result, "Revisor", False)["decision"], "rechazada")
        self.assertFalse(result.interrumpido)

    def test_skipped_stages_and_plain_text_cannot_approve(self):
        for responses in ([AIMessage(content="Aprobado")], [call("proponer_aprobacion")],
                          [call("task", dict(subagent_type="redactor", description="Aprobar"))]):
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                ejecutar_expediente(Path("E01"), model=ScriptedModel(responses=responses))

    def test_filesystem_tool_is_denied_without_running_and_flow_continues(self):
        responses = script(self.cases[0])
        responses.insert(1, call("ls", dict(path="/")))
        result = ejecutar_expediente(Path("E01"), model=ScriptedModel(responses=responses))
        denied = [m for m in result.graph.get_state(result.config).values["messages"]
                  if getattr(m, "tool_call_id", None) == "call-ls"]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].status, "error")
        self.assertIn("no autorizada", denied[0].content)
        self.assertTrue(result.interrumpido)
        self.assertEqual(result.dictamen.decision, "aprobar")

    def test_extractor_cannot_erase_a_quote(self):
        responses = script(self.cases[0])
        responses[4].tool_calls[0]["args"]["extracciones"].pop(0)
        with self.assertRaisesRegex(ValueError, "perdió"):
            ejecutar_expediente(Path("E01"), model=ScriptedModel(responses=responses))

    def test_classifier_can_identify_previously_unknown_documents(self):
        responses = script(self.cases[0])
        unknown = [d.model_copy(update={"tipo": "otro"})
                   for d in cargar_expediente(DATA / "expedientes" / "E01")]
        with patch("caso3.agentes.orquestador.cargar_expediente", return_value=unknown):
            result = ejecutar_expediente(Path("E01"), model=ScriptedModel(responses=responses))
        self.assertTrue(result.interrumpido)
        self.assertEqual(result.dictamen.decision, "aprobar")

    def test_auditor_and_redactor_cannot_erase_or_weaken_findings(self):
        for position, field, value, message in (
                (8, "hallazgos", [], "auditor"),
                (10, "hallazgos", [], "redactor")):
            responses = script(self.cases[4])
            responses[position].tool_calls[0]["args"][field] = value
            with self.subTest(stage=position), self.assertRaisesRegex(ValueError, message):
                ejecutar_expediente(Path("E05"), model=ScriptedModel(responses=responses))

    def test_extractor_cannot_hide_ambiguous_iva_or_change_winner(self):
        for case, field, value in ((self.cases[4], "iva_incluido", True),
                                   (self.cases[0], "items", []),
                                   (self.cases[0], "es_ganadora", False)):
            responses = script(case)
            responses[4].tool_calls[0]["args"]["extracciones"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "alteró"):
                ejecutar_expediente(Path(case["id"]), model=ScriptedModel(responses=responses))

    def test_revisions_are_counted_in_state_and_stop_at_two(self):
        base = script(self.cases[0])
        doubt = Hallazgo(codigo="INTERPRETACION", severidad="observacion",
                        detalle="Revisar la interpretación.", devolver_a="extractor")
        responses = base[:7]
        for turn in range(3):
            if turn:
                responses += base[3:7]
            responses += [call("task", dict(subagent_type="auditor", description="Revisar")),
                          call("Hallazgos", Hallazgos(hallazgos=[doubt]).model_dump(mode="json"))]
        findings = [doubt, Hallazgo(codigo="LIMITE_VUELTAS", severidad="bloqueante",
                                   detalle="Persisten dudas tras dos revisiones.")]
        verdict = Dictamen(decision="escalar", hallazgos=findings,
                           reglas=gold_rules(self.cases[0]), vueltas=2)
        responses += [base[9], call("Dictamen", verdict.model_dump(mode="json")), base[11]]
        result = ejecutar_expediente(Path("E01"), model=ScriptedModel(responses=responses))
        self.assertEqual(result.dictamen.vueltas, 2)
        self.assertEqual(result.dictamen.decision, "escalar")
        self.assertEqual(sum(p.agente == "auditor" for p in result.traza.pasos), 3)

    def test_each_subagent_can_run_alone_through_native_sdk(self):
        case = self.cases[0]
        responses = script(case)
        docs = cargar_expediente(DATA / "expedientes" / "E01")
        for role, position in zip(("clasificador", "extractor", "verificador", "auditor", "redactor"), (2, 4, 6, 8, 10)):
            expected = responses[position]
            with self.subTest(role=role):
                result = ejecutar_subagente(role, docs, date.fromisoformat(case["fecha"]),
                                             model=ScriptedModel(responses=[expected]))
                self.assertEqual(result.model_dump(mode="json"), expected.tool_calls[0]["args"])
