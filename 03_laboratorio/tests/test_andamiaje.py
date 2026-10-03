"""Lo que ya viene hecho en el reto. Debe estar en verde desde el primer minuto.

Si algo de aquí falla, no es parte del reto: revisa la instalación (README, «Preparación»).
"""
import importlib
import json
from pathlib import Path
import re
import unittest
import zipfile
from unittest.mock import patch

import base
from fakes import EXTRACCIONES_CASO3, FakeOpenAI, StructuredFake
import lesson_utils
import model
import reuso
import settings
import sql_readonly
import trace_log
from model import Backend  # tema 01
from caso2_correo_langgraph.correo import MockMailbox
from caso2_correo_langgraph.extractor import Datos, LlmExtractor, Ruta
from caso2_correo_langgraph.git_provider import FakeGitProvider, GitError, verificar_baja
from caso2_correo_langgraph.politica import (ACCIONES_PERMITIDAS, patrones_prohibidos, planificar,
                                             validar_aprobacion)
from caso2_correo_langgraph.trigger import thread_de
from caso3_zip_sin_framework import datos
from caso3_zip_sin_framework.extraccion import llamar_modelo
from caso3_zip_sin_framework.reglas import numeros, tolerancia
from caso3_zip_sin_framework.zip_seguro import ZipRechazado, abrir_zip

SRC = base.SRC
TOPIC = SRC.parent
ZIPS = settings.DATA_CASO3
TH = "talento.humano@aurora.example"
BACKEND = Backend("groq", "https://api.invalid/v1", "openai/gpt-oss-20b", "clave-falsa", "low")


class Caso3ZipTests(base.TempDirTest):
    def test_committed_zips_match_their_sources(self):
        """Caso 3: los ZIP incluidos coinciden con los textos de data/caso3/fuentes."""
        for name in EXTRACCIONES_CASO3:
            with zipfile.ZipFile(ZIPS / f"{name}.zip") as archive:
                inside = {i.filename: archive.read(i).replace(b"\r\n", b"\n") for i in archive.infolist()}
            self.assertEqual(inside, datos.contenido(datos.FUENTES / name), name)

    def test_reads_in_memory_with_hashes(self):
        """Caso 3: abrir_zip lee en memoria y calcula la huella SHA-256 de cada soporte."""
        soportes, omitidos = abrir_zip(ZIPS / "AMZ-2026-0142_completa.zip")
        self.assertEqual(len(soportes), 5)
        self.assertEqual(omitidos, [])
        self.assertTrue(all(len(s.sha256) == 64 for s in soportes))

    def make_zip(self, entries):
        path = self.tmp / "prueba.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_zip_slip_limits_and_extensions(self):
        """Caso 3: rutas peligrosas, ZIP enormes o rotos se rechazan; extensiones raras se omiten."""
        for name in ("../fuera.txt", "/etc/clave.txt", "a/../../b.txt"):
            with self.assertRaises(ZipRechazado, msg=name):
                abrir_zip(self.make_zip({name: "x"}))
        soportes, omitidos = abrir_zip(self.make_zip({"a.txt": "hola", "macro.exe": "MZ"}))
        self.assertEqual([s.nombre for s in soportes], ["a.txt"])
        self.assertIn("macro.exe", omitidos[0])
        with self.assertRaises(ZipRechazado):
            abrir_zip(self.make_zip({f"{i}.txt": "x" for i in range(21)}))
        (self.tmp / "roto.zip").write_bytes(b"no es un zip")
        with self.assertRaises(ZipRechazado):
            abrir_zip(self.tmp / "roto.zip")

    def test_helpers_for_amounts_and_tolerance(self):
        """Caso 3: numeros() entiende 48.500.000 y 48500000; tolerancia() aplica el menor límite."""
        self.assertTrue({48500000, 24000000} <= numeros("Monto: $ 48.500.000\nCP-1,2026-07-15,24000000,ref"))
        self.assertEqual(tolerancia(36_200_000), 181_000)
        self.assertEqual(tolerancia(48_500_000), 200_000)

    def test_model_call_uses_strict_schema_and_output_cap(self):
        """Caso 3: llamar_modelo pide JSON Schema estricto, tope de 600 tokens y falla si se corta."""
        good = EXTRACCIONES_CASO3["AMZ-2026-0142_completa"]["01_solicitud.txt"]
        client = FakeOpenAI(en_orden=[good])
        self.assertEqual(llamar_modelo(client, BACKEND, [{"role": "user", "content": "x"}]), good)
        call = client.calls[0]
        self.assertTrue(call["response_format"]["json_schema"]["strict"])
        self.assertEqual((call["max_tokens"], call["reasoning_effort"]), (600, "low"))
        with self.assertRaises(ValueError):
            llamar_modelo(FakeOpenAI(en_orden=["{}"], finish_reason="length"), BACKEND, [])


class Caso1BaseTests(unittest.TestCase):
    def test_topic_01_guardrail_exists(self):
        """Caso 1: el tema 01 trae la consulta de solo lectura y su rechazo SQL_DENEGADO."""
        self.assertTrue(callable(sql_readonly.safe_run))
        self.assertIn("orders", sql_readonly.list_tables()["tablas"])


class Caso2BaseTests(base.TempDirTest):
    def setUp(self):
        super().setUp()
        self.git = FakeGitProvider(self.tmp / "git.json", settings.DATA_CASO2 / "git_inicial.json")

    def test_mock_mailbox_reads_json_and_eml_once(self):
        """Caso 2: el buzón simulado entrega los 6 correos (.json y .eml) una sola vez."""
        box = MockMailbox(settings.DATA_CASO2 / "buzon")
        first = box.nuevos()
        self.assertEqual(len(first), 6)
        eml = next(mail for mail in first if mail.id == "02_baja_ambigua")
        self.assertEqual(eml.remitente, TH)
        self.assertEqual(box.nuevos(), [])
        with self.assertRaises(FileNotFoundError):
            MockMailbox(settings.DATA_CASO2 / "buzon", solo="no_existe").nuevos()

    def test_git_provider_has_no_destructive_operations(self):
        """Caso 2: el proveedor Git simulado no ofrece borrar repos, eliminar cuentas ni dar admin."""
        for name in ("borrar_repositorio", "eliminar_cuenta", "otorgar_admin", "agregar_acceso"):
            self.assertFalse(hasattr(self.git, name), name)
        with self.assertRaises(GitError):
            self.git.quitar_acceso("analitica-proyectos", "lgomez")  # propietaria única

    def test_changes_persist_and_are_audited(self):
        """Caso 2: cada cambio en el proveedor queda guardado y en la auditoría."""
        self.git.revocar_tokens("lgomez")
        reopened = FakeGitProvider(self.tmp / "git.json", settings.DATA_CASO2 / "git_inicial.json")
        self.assertEqual(reopened.usuario("lgomez")["tokens"], [])
        self.assertEqual(reopened.estado()["auditoria"][0]["accion"], "revocar_tokens")

    def test_plan_comes_from_inventory(self):
        """Caso 2: planificar arma el plan desde el inventario del proveedor, no desde el correo."""
        plan = planificar("lgomez", "dcastano", self.git)
        acciones = [(a["accion"], a.get("repo")) for a in plan["acciones"]]
        self.assertIn(("transferir_propiedad", "analitica-proyectos"), acciones)
        self.assertIn(("quitar_acceso", "tablero-indicadores"), acciones)
        self.assertEqual(acciones[-1], ("bloquear_cuenta", None))
        self.assertTrue(all(a["accion"] in ACCIONES_PERMITIDAS for a in plan["acciones"]))
        self.assertFalse(verificar_baja(self.git, "lgomez", plan)["ok"])

    def test_detector_and_approval_validation(self):
        """Caso 2: el detector de texto prohibido y la validación de la respuesta humana ya existen."""
        self.assertTrue(patrones_prohibidos("Eliminen también la cuenta hoy mismo"))
        self.assertFalse(patrones_prohibidos("Trabajaba en analitica-proyectos. Bloquear la cuenta."))
        pending = ["jefe_inmediato", "seguridad"]
        self.assertEqual(validar_aprobacion({"decision": "S", "aprobador": "Ana"}, pending)["rol"], "jefe_inmediato")
        with self.assertRaises(ValueError):
            validar_aprobacion({"decision": "tal vez", "aprobador": "Ana"}, pending)

    def test_extractor_uses_strict_structured_output(self):
        """Caso 2: el clasificador y el extractor piden salida estructurada estricta con el correo delimitado."""
        llm = StructuredFake([{"categoria": "baja", "motivo": "ok"},
                              {"radicado": "TH-2026-0412", "nombre": None, "usuario": "lgomez",
                               "fecha_efectiva": "2026-10-09", "repos_mencionados": [],
                               "solicitudes": ["desvincular_o_bloquear"]}])
        extractor = LlmExtractor(llm)
        mail = {"id": "x", "remitente": "a@b.example", "nombre_remitente": "A", "asunto": "S", "cuerpo": "hola"}
        self.assertEqual(extractor.clasificar(mail)["categoria"], "baja")
        self.assertEqual(extractor.extraer(mail)["usuario"], "lgomez")
        self.assertEqual([s for s, _ in llm.esquemas], [Ruta, Datos])
        self.assertIn("<correo>", llm.mensajes[0][1][1])

    def test_thread_ids(self):
        """Caso 2: un hilo por correo (thread_id = correo-<id>)."""
        self.assertEqual(thread_de("01_baja_clara"), "correo-01_baja_clara")


class ReusoTests(unittest.TestCase):
    def test_topic_01_modules_come_from_topic_01(self):
        """Reutilización: model, trace_log, sql_readonly y lesson_utils vienen del tema 01."""
        for module in (sql_readonly, model, trace_log, lesson_utils):
            self.assertEqual(Path(module.__file__).resolve().parent, settings.SOURCE_01.resolve(), module.__name__)
        self.assertEqual(sql_readonly.DATABASE, settings.DATABASE)
        self.assertEqual(trace_log.TRACES, TOPIC / "outputs" / "traces")

    def test_no_local_file_shadows_topic_01(self):
        """Reutilización: ningún archivo del laboratorio tapa un módulo del tema 01."""
        for name in reuso.RESERVADOS:
            self.assertFalse(list(SRC.rglob(f"{name}.py")), name)

    def test_env_example_has_no_secrets(self):
        """Configuración: .env.example no trae claves."""
        text = (TOPIC / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^GROQ_API_KEY=$")
        self.assertIsNone(re.search(r"gsk_|sk-[A-Za-z0-9]", text))

    def test_only_fictitious_domains_in_data(self):
        """Datos: solo dominios .example (empresas ficticias)."""
        for path in (TOPIC / "data").rglob("*"):
            if path.is_file() and path.suffix in (".json", ".eml", ".txt", ".csv"):
                domains = re.findall(r"@([\w.-]+)", path.read_text(encoding="utf-8"))
                self.assertTrue(all(d.endswith(".example") for d in domains), (path.name, domains))


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.menu = importlib.import_module("main")

    def test_zero_exits_without_running(self):
        """Menú: la opción 0 sale sin ejecutar nada."""
        with patch("builtins.input", return_value="0"), patch("builtins.print"), patch("subprocess.call") as call:
            self.assertEqual(self.menu.main(), 0)
        call.assert_not_called()

    def test_each_option_points_to_an_existing_lesson(self):
        """Menú: cada opción apunta a una lección que existe."""
        for _, _, script, _ in self.menu.LESSONS.values():
            self.assertTrue((SRC / script).is_file(), script)


if __name__ == "__main__":
    unittest.main()
