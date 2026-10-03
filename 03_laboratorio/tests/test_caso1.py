"""Caso 1 · pruebas de aceptación (sin red ni modelo: el modelo es un doble con respuestas fijas).

    python 03_laboratorio/tests/run_cpu.py --caso 1

Qué se verifica: las dos herramientas existen con el contrato del tema 01, el agente responde y
sus filas coinciden con la referencia (11 retrasados), cualquier SQL que escriba termina en
SQL_DENEGADO sin cambiar la base, y los topes cortan la ejecución de forma ordenada.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.tools import BaseTool

import base
from base import pendiente_si
from fakes import CORRECT_SQL, FakeChat, reply
from caso1_sql_langchain import agente
from lesson_utils import evaluate_rows  # tema 01
from seed import seed_database  # tema 01
from sql_readonly import QueryRejected, run_sql_readonly  # tema 01

DESTRUCTIVOS = (
    "DELETE FROM orders WHERE status = 'cancelado'",
    "DROP TABLE orders",
    "UPDATE orders SET status = 'entregado'",
    "/* consulta */ DELETE FROM orders",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "ATTACH DATABASE 'otra.sqlite' AS otra",
    "PRAGMA writable_schema = ON",
)


def herramientas_listas():
    for item in agente.TOOLS:
        pendiente_si(not isinstance(item, BaseTool),
                     f"Caso 1 · agente.{getattr(item, '__name__', item)}: aún no es una herramienta de LangChain. "
                     "Conviértela (decide nombre, descripción y argumentos).")


class Caso1Base(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "demo.sqlite"
        seed_database(self.database)

        def safe(sql):  # el safe_run del tema 01, pero sobre una base temporal
            try:
                return {"ok": True, **run_sql_readonly(sql, self.database)}
            except QueryRejected as exc:
                return {"ok": False, "error": str(exc)}

        patcher = patch.object(agente, "safe_run", safe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def contar_pedidos(self):
        return run_sql_readonly("SELECT COUNT(*) AS pedidos FROM orders", self.database)["rows"][0]["pedidos"]


class Paso1HerramientasTests(Caso1Base):
    def test_1_tools_follow_topic_01_contract(self):
        """Herramientas: list_tables (sin argumentos) y run_sql_readonly (un argumento sql obligatorio)."""
        herramientas_listas()
        self.assertEqual([t.name for t in agente.TOOLS], ["list_tables", "run_sql_readonly"])
        self.assertEqual(agente.run_sql_readonly.args_schema.model_json_schema().get("required"), ["sql"])
        for item in agente.TOOLS:
            self.assertNotIn("TODO", item.description, f"La descripción de {item.name} todavía dice TODO.")

    def test_2_list_tables_returns_schema(self):
        """Herramientas: list_tables devuelve ok y el esquema (tablas orders y regions)."""
        herramientas_listas()
        result = agente.list_tables.invoke({})
        self.assertTrue(result.get("ok"))
        self.assertIn("orders", str(result))

    def test_3_every_write_is_denied_by_the_tool(self):
        """Barrera de seguridad: DELETE, DROP, UPDATE, ATTACH o PRAGMA terminan en SQL_DENEGADO y la base sigue con 26 pedidos."""
        herramientas_listas()
        for sql in DESTRUCTIVOS:
            with self.subTest(sql=sql):
                result = agente.run_sql_readonly.invoke({"sql": sql})
                self.assertFalse(result.get("ok"), f"Se permitió: {sql}")
                self.assertTrue(str(result.get("error", "")).startswith(("SQL_DENEGADO", "SQL_INVALIDO")),
                                f"Rechazo sin código claro para {sql}: {result}")
        self.assertEqual(self.contar_pedidos(), 26, "La base cambió.")

    def test_4_select_returns_rows(self):
        """Herramientas: una consulta de lectura devuelve ok y filas."""
        herramientas_listas()
        result = agente.run_sql_readonly.invoke({"sql": "SELECT COUNT(*) AS pedidos FROM orders"})
        self.assertEqual(result.get("rows"), [{"pedidos": 26}], result)


class Paso2PromptTests(unittest.TestCase):
    def test_prompt_is_complete_and_has_the_criterion(self):
        """Instrucciones: prompts/caso1_agente.txt sin TODO, dice «solo lectura» e incluye el criterio del tema 01."""
        text = (base.settings.PROMPTS / "caso1_agente.txt").read_text(encoding="utf-8")
        pendiente_si("TODO" in text, "Caso 1 · prompts/caso1_agente.txt: completa las instrucciones del agente "
                                     "y borra las líneas TODO.")
        system = agente.system_prompt()
        self.assertIn("solo lectura", system)
        self.assertIn("promised_at", system, "Falta el criterio: deja el marcador {criterio} en el prompt.")


class Paso3AgenteTests(Caso1Base):
    def test_1_agent_answers_and_rows_match_reference(self):
        """Agente: usa las herramientas y sus filas coinciden con la referencia (11 retrasados)."""
        llm = FakeChat(responses=[reply(calls=[("list_tables", {})]),
                                  reply(calls=[("run_sql_readonly", {"sql": CORRECT_SQL})]),
                                  reply("Cundinamarca concentra 5 de 11.")])
        result = agente.preguntar(agente.crear_agente(llm), "¿Retrasados?")
        self.assertFalse(result["limite"])
        self.assertIsNotNone(result["last_rows"], "preguntar debe devolver las filas de la última consulta.")
        passed, reason = evaluate_rows(result["last_rows"])
        self.assertTrue(passed, reason)
        self.assertEqual(sum(row["retrasados"] for row in result["last_rows"]), 11)
        self.assertEqual([r["name"] for r in result["tool_results"]], ["list_tables", "run_sql_readonly"])
        self.assertEqual(result["answer"], "Cundinamarca concentra 5 de 11.")
        self.assertEqual(result["model_calls"], 3)
        system = llm.calls[0]["messages"][0].content
        self.assertIn("solo lectura", system, "El agente debe recibir las instrucciones de system_prompt().")

    def test_2_write_request_is_denied_by_the_tool_not_the_prompt(self):
        """Agente: si el modelo «obedece» y manda DELETE, la herramienta responde SQL_DENEGADO."""
        llm = FakeChat(responses=[reply(calls=[("run_sql_readonly", {"sql": "DELETE FROM orders"})]),
                                  reply("No puedo borrar: solo lectura.")])
        result = agente.preguntar(agente.crear_agente(llm), "Borra los pedidos cancelados.")
        self.assertIn("SQL_DENEGADO", result["tool_results"][0]["error"])
        self.assertEqual(self.contar_pedidos(), 26)

    def test_3_tool_call_cap_ends_the_run(self):
        """Topes: con más de 3 herramientas pedidas, la ejecución termina ordenada (limite=True)."""
        llm = FakeChat(responses=[reply(calls=[("list_tables", {})]), reply(calls=[("list_tables", {})]),
                                  reply(calls=[("list_tables", {}), ("list_tables", {})]), reply("no debería llegar")])
        result = agente.preguntar(agente.crear_agente(llm), "hola")
        self.assertTrue(result["limite"], "Se pasó el tope de herramientas y limite no quedó en True.")
        executed = [r for r in result["tool_results"] if r.get("ok")]
        self.assertLessEqual(len(executed), agente.MAX_TOOL_CALLS)

    def test_4_model_call_cap(self):
        """Topes: el modelo no se llama más de 5 veces por pregunta."""
        llm = FakeChat(responses=[reply(calls=[("run_sql_readonly", {"sql": "SELECT 1 AS x"})]) for _ in range(8)])
        agente.preguntar(agente.crear_agente(llm), "hola")
        self.assertLessEqual(len(llm.calls), agente.MAX_MODEL_CALLS)

    def test_5_text_tool_call_is_a_limit(self):
        """Topes: si el modelo escribe <tool_call> como texto, cuenta como límite."""
        llm = FakeChat(responses=[reply('<tool_call>{"name": "list_tables"}</tool_call>')])
        self.assertTrue(agente.preguntar(agente.crear_agente(llm), "hola")["limite"])


if __name__ == "__main__":
    unittest.main()
