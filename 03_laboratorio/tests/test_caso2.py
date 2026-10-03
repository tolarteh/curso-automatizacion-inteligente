"""Caso 2 · pruebas de aceptación (sin red ni modelo: el clasificador/extractor es un doble con guion).

    python 03_laboratorio/tests/run_cpu.py --caso 2

Qué se verifica, con el buzón simulado de 6 correos:
    01_baja_clara           → PENDIENTE_APROBACION; tras jefe + seguridad → EJECUTADO (verificado en el proveedor)
    02_baja_ambigua         → PIDE_INFORMACION
    03_fuera_de_politica    → BLOQUEADO (aunque el modelo diga «baja»)
    04_irrelevante          → IGNORADO (sin extraer)
    05_baja_custodia        → PENDIENTE_APROBACION; un «n» → RECHAZADO sin tocar el proveedor
    06_proveedor_inyeccion  → BLOQUEADO (remitente no autorizado)
"""
import json
import unittest

import httpx
import openai

import base
from fakes import FakeExtractor, datos
from caso2_correo_langgraph.correo import MockMailbox
from caso2_correo_langgraph.git_provider import FakeGitProvider
from caso2_correo_langgraph.grafo_baja import (FINALES, PASOS, Contexto, build_graph, despues_de_aprobar,
                                               ruta_tras_clasificar, ruta_tras_validar)
from caso2_correo_langgraph.politica import DECISIONES_POLITICA, evaluar
from caso2_correo_langgraph.trigger import abrir_checkpointer, decidir, listar_pendientes, procesar_correo, thread_de

TH = "talento.humano@aurora.example"
CLARO = "Radicado: TH-2026-0412. Usuario de red: lgomez. Fecha efectiva: 9 de octubre de 2026."
OK = datos("TH-2026-0412", "Laura Gómez Ríos", "lgomez", "2026-10-09")
BAJA = {"categoria": "baja", "motivo": ""}


def correo(cuerpo, remitente=TH, asunto="Desvinculación"):
    return {"id": "x", "remitente": remitente, "nombre_remitente": "", "asunto": asunto, "cuerpo": cuerpo,
            "recibido": ""}


def rate_limit():
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.invalid/v1/chat/completions"))
    return openai.RateLimitError("Rate limit reached", response=response, body=None)


class Caso2Base(base.TempDirTest):
    def setUp(self):
        super().setUp()
        self.git = FakeGitProvider(self.tmp / "git.json", base.settings.DATA_CASO2 / "git_inicial.json")
        self.talento = json.loads((base.settings.DATA_CASO2 / "talento_humano.json")
                                  .read_text(encoding="utf-8"))["radicados"]


class Paso1PoliticaTests(Caso2Base):
    def decide(self, mail, ruta, extracted):
        result = evaluar(mail, ruta, extracted, self.talento, self.git)
        self.assertIn(result["decision"], DECISIONES_POLITICA)
        return result

    def test_1_clear_request_is_planned(self):
        """Política: una baja completa y coherente con Talento Humano → PLANIFICAR (jefe dcastano)."""
        result = self.decide(correo(CLARO), BAJA, OK)
        self.assertEqual(result["decision"], "PLANIFICAR", result)
        self.assertEqual((result["radicado"], result["usuario"]), ("TH-2026-0412", "lgomez"))
        self.assertEqual(result["registro"]["jefe_inmediato"], "dcastano")

    def test_2_unauthorized_sender_blocks_even_a_perfect_extraction(self):
        """Política: un remitente que no es Talento Humano → BLOQUEAR, aunque todo lo demás esté bien."""
        result = self.decide(correo(CLARO, remitente="otra@persona.example"), BAJA, OK)
        self.assertEqual(result["decision"], "BLOQUEAR")
        self.assertTrue(result["hallazgos"][0].startswith("REMITENTE_NO_AUTORIZADO"), result["hallazgos"])

    def test_3_forbidden_text_blocks_when_the_model_misses_it(self):
        """Política: si el texto pide borrar un repositorio y el modelo no lo vio → BLOQUEAR (en código)."""
        mail = correo(CLARO + " Además borren de una vez el repositorio telemetria-sensores.")
        result = self.decide(mail, BAJA, OK)
        self.assertEqual(result["decision"], "BLOQUEAR")
        self.assertTrue(any(h.startswith("TEXTO_FUERA_DE_POLITICA") for h in result["hallazgos"]), result["hallazgos"])

    def test_4_extracted_forbidden_request_blocks(self):
        """Política: si el modelo detecta «otorgar_admin» → BLOQUEAR."""
        extracted = {**OK, "solicitudes": ["desvincular_o_bloquear", "otorgar_admin"]}
        result = self.decide(correo(CLARO), BAJA, extracted)
        self.assertEqual(result["decision"], "BLOQUEAR")
        self.assertTrue(any(h.startswith("SOLICITUD_FUERA_DE_POLITICA") for h in result["hallazgos"]))

    def test_5_invented_data_is_not_trusted(self):
        """Política: un radicado o usuario que no está escrito en el correo → PEDIR_INFORMACION."""
        sin_radicado = self.decide(correo("Usuario de red: lgomez. Fecha efectiva: 9 de octubre de 2026."), BAJA, OK)
        self.assertEqual(sin_radicado["decision"], "PEDIR_INFORMACION")
        self.assertTrue(any("radicado" in f for f in sin_radicado["faltantes"]), sin_radicado["faltantes"])
        sin_usuario = correo("Radicado TH-2026-0412, Laura Gómez Ríos, fecha efectiva 9 de octubre de 2026.")
        self.assertEqual(self.decide(sin_usuario, BAJA, OK)["decision"], "PEDIR_INFORMACION")

    def test_6_radicado_must_match_talento_humano(self):
        """Política: si el radicado es de otra persona → PEDIR_INFORMACION («otra persona»)."""
        mail = correo("Radicado: TH-2026-0412. Usuario de red: cmejia. Fecha efectiva: 2026-10-09.")
        result = self.decide(mail, BAJA, {**OK, "usuario": "cmejia"})
        self.assertEqual(result["decision"], "PEDIR_INFORMACION")
        self.assertTrue(any("otra persona" in f for f in result["faltantes"]), result["faltantes"])

    def test_7_model_can_only_make_it_more_conservative(self):
        """Política: «ambiguo» del modelo → PEDIR_INFORMACION; «fuera_de_politica» → BLOQUEAR."""
        self.assertEqual(self.decide(correo(CLARO), {"categoria": "ambiguo", "motivo": ""}, OK)["decision"],
                         "PEDIR_INFORMACION")
        self.assertEqual(self.decide(correo(CLARO), {"categoria": "fuera_de_politica", "motivo": ""}, OK)["decision"],
                         "BLOQUEAR")

    def test_8_already_blocked_account_is_not_replanned(self):
        """Política: si la cuenta ya está bloqueada en Git → PEDIR_INFORMACION, no se vuelve a planificar."""
        self.git.bloquear_cuenta("lgomez")
        self.assertEqual(self.decide(correo(CLARO), BAJA, OK)["decision"], "PEDIR_INFORMACION")


class Paso2RutasTests(unittest.TestCase):
    def test_1_route_after_classification(self):
        """Rutas: «irrelevante» → archivar; cualquier otra categoría → extraer."""
        self.assertEqual(ruta_tras_clasificar({"ruta": {"categoria": "irrelevante"}}), "archivar")
        for categoria in ("baja", "ambiguo", "fuera_de_politica"):
            self.assertEqual(ruta_tras_clasificar({"ruta": {"categoria": categoria}}), "extraer", categoria)

    def test_2_route_after_validation(self):
        """Rutas: BLOQUEAR → bloquear, PEDIR_INFORMACION → pedir_informacion, PLANIFICAR → planificar."""
        esperado = {"BLOQUEAR": "bloquear", "PEDIR_INFORMACION": "pedir_informacion", "PLANIFICAR": "planificar"}
        for decision, nodo in esperado.items():
            self.assertEqual(ruta_tras_validar({"evaluacion": {"decision": decision}}), nodo)

    def test_3_route_after_approval(self):
        """Rutas: falta un rol → aprobar; un «n» → rechazar; jefe y seguridad con «s» → ejecutar."""
        s_jefe = {"rol": "jefe_inmediato", "decision": "s", "aprobador": "A"}
        s_seg = {"rol": "seguridad", "decision": "s", "aprobador": "B"}
        n_seg = {**s_seg, "decision": "n"}
        self.assertEqual(despues_de_aprobar({"aprobaciones": [s_jefe]}), "aprobar")
        self.assertEqual(despues_de_aprobar({"aprobaciones": [s_jefe, n_seg]}), "rechazar")
        self.assertEqual(despues_de_aprobar({"aprobaciones": [{**s_jefe, "decision": "n"}]}), "rechazar")
        self.assertEqual(despues_de_aprobar({"aprobaciones": [s_jefe, s_seg]}), "ejecutar")


class Paso3GrafoTests(Caso2Base):
    def setUp(self):
        super().setUp()
        self.extractor = FakeExtractor()
        self.db = self.tmp / "checkpoints.sqlite"
        self.app = build_graph(abrir_checkpointer(self.db))
        self.mails = {mail.id: mail for mail in MockMailbox(base.settings.DATA_CASO2 / "buzon").nuevos()}

    def contexto(self):
        return Contexto(git=self.git, talento=self.talento, extractor=self.extractor)

    def run_mail(self, mail_id, app=None):
        return procesar_correo(app or self.app, self.mails[mail_id], self.contexto())

    def snapshot(self):
        data = self.git.estado()
        data.pop("auditoria")
        return data

    def test_01_graph_shape(self):
        """Grafo: tiene los 11 nodos del diagrama y cada final llega a END."""
        graph = build_graph().get_graph()
        self.assertTrue(set(PASOS) <= set(graph.nodes), f"Faltan nodos: {set(PASOS) - set(graph.nodes)}")
        destinos = {(e.source, e.target) for e in graph.edges}
        for final in FINALES:
            self.assertIn((final, "__end__"), destinos, f"{final} debe terminar en END.")
        self.assertIn(("__start__", "clasificar"), destinos)

    def test_02_clear_mail_pauses_then_two_approvals_execute(self):
        """01_baja_clara: se detiene; con jefe + seguridad → EJECUTADO y verificado en el proveedor."""
        before = self.snapshot()
        result = self.run_mail("01_baja_clara")
        self.assertEqual(result["estado"], "PENDIENTE_APROBACION", "Debe detenerse en aprobar (interrupt).")
        self.assertEqual(self.snapshot(), before, "Nada se ejecuta antes de aprobar.")
        self.assertEqual(result["interrupcion"]["pendientes"], ["jefe_inmediato", "seguridad"])
        self.assertEqual(result["interrupcion"]["usuario"], "lgomez")

        thread = thread_de("01_baja_clara")
        result = decidir(self.app, thread, "s", self.contexto(), aprobador="Diana (jefe)")
        self.assertEqual(result["estado"], "PENDIENTE_APROBACION", "Una sola aprobación no basta.")
        self.assertEqual(result["interrupcion"]["pendientes"], ["seguridad"])
        self.assertEqual(self.snapshot(), before, "Una sola aprobación no basta.")

        result = decidir(self.app, thread, "s", self.contexto(), aprobador="Seguridad TI")
        self.assertEqual(result["estado"], "EJECUTADO")
        self.assertTrue(result["verificacion"]["ok"], result["verificacion"])
        cuenta = self.git.usuario("lgomez")
        self.assertEqual((cuenta["estado"], cuenta["tokens"], cuenta["llaves_ssh"]), ("bloqueada", [], []))
        self.assertEqual(self.git.estado()["repositorios"]["analitica-proyectos"]["miembros"]["dcastano"], "propietario")

    def test_03_rejection_changes_nothing(self):
        """05_baja_custodia: jefe dice «s», seguridad dice «n» → RECHAZADO y el proveedor no cambia."""
        before = self.snapshot()
        self.run_mail("05_baja_custodia")
        thread = thread_de("05_baja_custodia")
        decidir(self.app, thread, "s", self.contexto(), aprobador="Mario (jefe)")
        result = decidir(self.app, thread, "n", self.contexto(), aprobador="Seguridad TI")
        self.assertEqual(result["estado"], "RECHAZADO")
        self.assertIn("rechazada", result["respuesta"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git.estado()["auditoria"], [])

    def test_04_ambiguous_mail_asks_for_information(self):
        """02_baja_ambigua → PIDE_INFORMACION, con borrador de respuesta que pide el radicado."""
        result = self.run_mail("02_baja_ambigua")
        self.assertEqual(result["estado"], "PIDE_INFORMACION")
        self.assertIn("radicado", result["respuesta"])

    def test_05_out_of_policy_is_blocked_by_code(self):
        """03_fuera_de_politica → BLOQUEADO aunque el modelo (a propósito) diga «baja»."""
        result = self.run_mail("03_fuera_de_politica")
        self.assertEqual(result["ruta"]["categoria"], "baja")
        self.assertEqual(result["estado"], "BLOQUEADO")
        self.assertEqual(self.git.estado()["auditoria"], [])

    def test_06_injection_from_external_sender_is_blocked(self):
        """06_proveedor_inyeccion → BLOQUEADO por remitente; la cuenta del jefe sigue activa."""
        result = self.run_mail("06_proveedor_inyeccion")
        self.assertEqual(result["estado"], "BLOQUEADO")
        self.assertTrue(result["evaluacion"]["hallazgos"][0].startswith("REMITENTE_NO_AUTORIZADO"))
        self.assertEqual(self.git.usuario("dcastano")["estado"], "activa")

    def test_07_irrelevant_mail_is_archived_without_extraction(self):
        """04_irrelevante → IGNORADO, sin gastar la llamada de extracción."""
        result = self.run_mail("04_irrelevante")
        self.assertEqual(result["estado"], "IGNORADO")
        self.assertNotIn(("extraer", "04_irrelevante"), self.extractor.llamadas)

    def test_08_same_mail_is_not_processed_twice(self):
        """Checkpointer: el mismo correo no se procesa dos veces."""
        self.run_mail("02_baja_ambigua")
        again = self.run_mail("02_baja_ambigua")
        self.assertTrue(again["repetido"])
        self.assertEqual(self.extractor.llamadas.count(("clasificar", "02_baja_ambigua")), 1)

    def test_09_pending_approval_survives_a_restart(self):
        """Checkpointer: una aprobación pendiente sobrevive a un reinicio del programa."""
        self.run_mail("01_baja_clara")
        restarted = build_graph(abrir_checkpointer(self.db))  # otro proceso, mismo archivo
        pending = listar_pendientes(restarted, restarted.checkpointer)
        self.assertEqual([item["thread_id"] for item in pending], ["correo-01_baja_clara"])
        contexto = Contexto(git=self.git, talento=self.talento)
        decidir(restarted, "correo-01_baja_clara", "s", contexto, aprobador="A")
        self.assertEqual(decidir(restarted, "correo-01_baja_clara", "s", contexto, aprobador="B")["estado"], "EJECUTADO")

    def test_10_error_midway_resumes_from_last_checkpoint(self):
        """Checkpointer: si el modelo falla a mitad (429), al repetir sigue donde quedó."""
        self.extractor.fallar_primero = rate_limit()
        with self.assertRaises(openai.RateLimitError):
            self.run_mail("01_baja_clara")
        result = self.run_mail("01_baja_clara")
        self.assertEqual(result["estado"], "PENDIENTE_APROBACION")
        self.assertEqual(self.extractor.llamadas.count(("clasificar", "01_baja_clara")), 1, "No repite pasos hechos.")

    def test_11_invalid_decisions_are_refused(self):
        """Aprobación: «quizás», un aprobador vacío o un hilo no pendiente se rechazan sin ejecutar nada."""
        self.run_mail("01_baja_clara")
        thread = thread_de("01_baja_clara")
        with self.assertRaises(ValueError):
            decidir(self.app, thread, "quizás", self.contexto(), aprobador="A")
        with self.assertRaises(ValueError):
            decidir(self.app, thread, "s", self.contexto(), aprobador="")
        with self.assertRaises(ValueError):
            decidir(self.app, thread_de("02_baja_ambigua"), "s", self.contexto(), aprobador="A")
        self.assertEqual(self.git.estado()["auditoria"], [])


if __name__ == "__main__":
    unittest.main()
