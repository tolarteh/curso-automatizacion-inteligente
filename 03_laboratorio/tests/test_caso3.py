"""Caso 3 · pruebas de aceptación (sin red ni modelo: el modelo es un doble con respuestas fijas).

    python 03_laboratorio/tests/run_cpu.py --caso 3

Qué se verifica: el evaluador detecta extracciones inventadas, el bucle corrige con la crítica
(máximo 2 intentos) y las reglas llevan cada ZIP a su decisión de negocio:
    AMZ-2026-0142_completa → LISTA_PARA_APROBACION
    AMZ-2026-0157_diferencia → EN_REVISION
    AMZ-2026-0163_incompleta → DEVOLVER
"""
import json
import unittest

import base
from base import Recorder
from fakes import EXTRACCIONES_CASO3, FakeOpenAI, soporte
from model import Backend  # tema 01
from caso3_zip_sin_framework import datos
from caso3_zip_sin_framework.extraccion import MAX_INTENTOS, extraer_documento
from caso3_zip_sin_framework.pipeline import guardar, procesar_zip
from caso3_zip_sin_framework.reglas import DECISIONES, decidir, evaluar_extraccion

BACKEND = Backend("groq", "https://api.invalid/v1", "openai/gpt-oss-20b", "clave-falsa", "low")
ZIPS = base.settings.DATA_CASO3
SOLICITUD = (datos.FUENTES / "AMZ-2026-0142_completa" / "01_solicitud.txt").read_text(encoding="utf-8")
ESPERADO = {"AMZ-2026-0142_completa": "LISTA_PARA_APROBACION", "AMZ-2026-0157_diferencia": "EN_REVISION",
            "AMZ-2026-0163_incompleta": "DEVOLVER"}


def docs(name, **verificado):
    """Los soportes de un ZIP ya extraídos (como los arma el pipeline)."""
    result = []
    for nombre, extraccion in EXTRACCIONES_CASO3[name].items():
        texto = (datos.FUENTES / name / nombre).read_text(encoding="utf-8")
        result.append({"nombre": nombre, "extraccion": extraccion, "texto": texto,
                       "verificado": verificado.get(nombre, True)})
    return result


class Paso1EvaluadorTests(unittest.TestCase):
    def test_1_correct_extraction_has_no_problems(self):
        """Evaluador: una extracción correcta no tiene problemas (lista vacía)."""
        good = EXTRACCIONES_CASO3["AMZ-2026-0142_completa"]["01_solicitud.txt"]
        self.assertEqual(evaluar_extraccion(SOLICITUD, good), [],
                         "La extracción correcta de 01_solicitud.txt no debería tener problemas.")

    def test_2_invented_amount_and_date_are_caught(self):
        """Evaluador: un monto y una fecha que no están escritos en el documento se detectan."""
        bad = soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-21", 48000000, desembolsos=2)
        problems = evaluar_extraccion(SOLICITUD, bad)
        self.assertTrue(any("48000000" in p for p in problems), f"Debe nombrar el monto 48000000. Obtuve: {problems}")
        self.assertTrue(any("2026-09-21" in p for p in problems), f"Debe nombrar la fecha 2026-09-21. Obtuve: {problems}")

    def test_3_similar_code_is_not_the_catalog_code(self):
        """Evaluador: «FAC-AMZ-09» no es un formato del catálogo; el tipo correcto es OTRO."""
        text = "ANEXO\nFormato: FAC-AMZ-09\nFactura por $ 6.375.000"
        self.assertTrue(evaluar_extraccion(text, soporte("FACTURA", "FAC-AMZ-09")),
                        "Un documento con Formato: FAC-AMZ-09 marcado como FACTURA debe tener problemas.")
        self.assertEqual(evaluar_extraccion(text, soporte("OTRO", "FAC-AMZ-09")), [])
        self.assertTrue(evaluar_extraccion("Sin código", soporte("DEM-AMZ-05", "DEM-AMZ-05")),
                        "Un tipo DEM-AMZ-xx exige que el código esté escrito en el documento.")

    def test_4_required_fields_by_type(self):
        """Evaluador: una solicitud DEM-AMZ-03 sin monto solicitado tiene problemas."""
        incompleta = soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-22", None, desembolsos=2)
        self.assertTrue(evaluar_extraccion(SOLICITUD, incompleta), "Falta monto_solicitado y no se detectó.")


class Paso2BucleTests(unittest.TestCase):
    def test_1_feedback_fixes_on_second_attempt(self):
        """Evaluador-optimizador: el 2.º intento recibe la crítica y queda verificado."""
        good = EXTRACCIONES_CASO3["AMZ-2026-0142_completa"]["01_solicitud.txt"]
        bad = {**good, "monto_solicitado": 48000000}
        client, trace = FakeOpenAI(en_orden=[bad, good]), Recorder()
        result = extraer_documento(client, BACKEND, "01_solicitud.txt", SOLICITUD, trace)
        self.assertTrue(result["verificado"], "Tras la corrección, el soporte debe quedar verificado.")
        self.assertEqual(result["intentos"], 2)
        self.assertEqual(len(client.calls), 2)
        feedback = json.dumps(client.calls[1]["messages"][2:], ensure_ascii=False)
        self.assertIn("48000000", feedback, "El reintento debe mostrarle al modelo el problema (el monto 48000000).")
        self.assertIn("<documento", client.calls[0]["messages"][1]["content"], "El documento va delimitado.")
        self.assertEqual(result["nombre"], "01_solicitud.txt")
        self.assertEqual(len(result["historial"]), 2)

    def test_2_gives_up_after_max_attempts(self):
        """Evaluador-optimizador: no insiste más de MAX_INTENTOS veces; queda NO verificado."""
        bad = soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-22", 1, desembolsos=2)
        client = FakeOpenAI(en_orden=[bad] * 5)
        result = extraer_documento(client, BACKEND, "01_solicitud.txt", SOLICITUD)
        self.assertFalse(result["verificado"])
        self.assertEqual(len(client.calls), MAX_INTENTOS, f"Se esperaban {MAX_INTENTOS} llamadas al modelo.")
        self.assertTrue(result["problemas"])

    def test_3_invalid_json_is_a_failed_attempt(self):
        """Evaluador-optimizador: una respuesta que no es JSON cuenta como intento fallido, no rompe."""
        good = EXTRACCIONES_CASO3["AMZ-2026-0142_completa"]["01_solicitud.txt"]
        result = extraer_documento(FakeOpenAI(en_orden=["no json", good]), BACKEND, "01_solicitud.txt", SOLICITUD)
        self.assertTrue(result["verificado"])
        self.assertEqual(result["intentos"], 2)

    def test_4_one_call_when_first_attempt_is_good(self):
        """Evaluador-optimizador: si el primer intento está bien, no se vuelve a llamar al modelo."""
        good = EXTRACCIONES_CASO3["AMZ-2026-0142_completa"]["01_solicitud.txt"]
        client = FakeOpenAI(en_orden=[good, good])
        self.assertTrue(extraer_documento(client, BACKEND, "01_solicitud.txt", SOLICITUD)["verificado"])
        self.assertEqual(len(client.calls), 1)


class Paso3ReglasTests(unittest.TestCase):
    def test_1_complete_zip_is_ready_for_approval(self):
        """Reglas: AMZ-2026-0142_completa → LISTA_PARA_APROBACION (diferencia 80.000 dentro de tolerancia)."""
        result = decidir(docs("AMZ-2026-0142_completa"))
        self.assertEqual(result["decision"], "LISTA_PARA_APROBACION", result.get("motivos"))
        self.assertEqual(result["cruce"]["diferencia"], 80_000)
        self.assertTrue(result["cruce"]["dentro_de_tolerancia"])

    def test_2_difference_goes_to_review(self):
        """Reglas: AMZ-2026-0157_diferencia → EN_REVISION (190.000 supera la tolerancia de 181.000)."""
        result = decidir(docs("AMZ-2026-0157_diferencia"))
        self.assertEqual(result["decision"], "EN_REVISION", result.get("motivos"))
        self.assertEqual((result["cruce"]["diferencia"], result["cruce"]["tolerancia"]), (190_000, 181_000))

    def test_3_incomplete_zip_is_returned(self):
        """Reglas: AMZ-2026-0163_incompleta → DEVOLVER (faltan FACTURA y DEM-AMZ-07; certificación de 57 días)."""
        result = decidir(docs("AMZ-2026-0163_incompleta"))
        self.assertEqual(result["decision"], "DEVOLVER", result.get("motivos"))
        self.assertEqual(set(result["faltantes"]), {"FACTURA", "DEM-AMZ-07"})
        self.assertTrue(any("57 días" in m for m in result["motivos"]), f"Motivos: {result['motivos']}")
        self.assertTrue(any("FAC-AMZ-09" in o for o in result["observaciones"]),
                        f"Observaciones: {result['observaciones']}")

    def test_4_unverified_support_goes_to_human_review(self):
        """Reglas: un soporte NO verificado va a revisión humana (EN_REVISION), no se da por faltante."""
        result = decidir(docs("AMZ-2026-0142_completa", **{"05_comprobantes_pago.csv": False}))
        self.assertEqual(result["decision"], "EN_REVISION")
        self.assertEqual(result["faltantes"], [])

    def test_5_system_never_approves(self):
        """Reglas: el sistema solo sugiere; la aprobación es de una persona."""
        for name in ESPERADO:
            result = decidir(docs(name))
            self.assertIn(result["decision"], DECISIONES)
            self.assertIn("persona", result["responsable"])


class Paso4PipelineTests(base.TempDirTest):
    def test_end_to_end_for_the_three_zips(self):
        """De punta a punta: los tres ZIP llegan a su decisión, un trabajador por soporte y resumen con SHA-256."""
        for name, decision in ESPERADO.items():
            client = FakeOpenAI(por_documento=EXTRACCIONES_CASO3[name])
            result = procesar_zip(ZIPS / f"{name}.zip", client, BACKEND, Recorder(), mostrar=lambda *_: None)
            self.assertEqual(result["decision"], decision, name)
            self.assertEqual(len(client.calls), len(EXTRACCIONES_CASO3[name]), "Una llamada por soporte.")
            _, md_path = guardar(result, self.tmp)
            summary = md_path.read_text(encoding="utf-8")
            self.assertIn(decision, summary)
            self.assertIn(result["documentos"][0]["sha256"], summary)


if __name__ == "__main__":
    unittest.main()
