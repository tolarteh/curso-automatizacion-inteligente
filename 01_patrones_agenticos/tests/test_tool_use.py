import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import CORRECT_SQL, FakeLlm, response
from seed import seed_database
from sql_readonly import QueryRejected, run_sql_readonly

tool_use = importlib.import_module("02_tool_use")


class ToolUseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "demo.sqlite"
        seed_database(database)

        def safe(sql):
            try:
                return {"ok": True, **run_sql_readonly(sql, database)}
            except QueryRejected as exc:
                return {"ok": False, "error": str(exc)}

        patcher = patch.object(tool_use, "safe_run", safe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_real_protocol_messages_and_exact_rows(self):
        llm = FakeLlm([response(calls=[("list_tables", "{}")]),
                       response(calls=[("run_sql_readonly", json.dumps({"sql": CORRECT_SQL}))]),
                       response("11 retrasados, Cundinamarca 5.")])
        result = tool_use.run(llm, Mock())
        self.assertEqual(result["tool_calls"], 2)
        self.assertTrue(result["verified"])
        messages = llm.calls[1]["messages"]
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["tool_call_id"], messages[-2]["tool_calls"][0]["id"])

    def test_arguments_and_unknown_tools_are_explicit_errors(self):
        for name, raw in (("list_tables", "[]"), ("list_tables", '{"extra": 1}'),
                          ("run_sql_readonly", "{}"), ("run_sql_readonly", '{"sql": 1}'),
                          ("run_sql_readonly", "{bad"), ("list_tables", None), ("unknown", "{}")):
            with self.subTest(name=name, raw=raw):
                self.assertFalse(tool_use.dispatch(name, raw)["ok"])

    def test_consecutive_errors_stop(self):
        llm = FakeLlm([response(calls=[("unknown", "{}"), ("unknown", "{}")])])
        with self.assertRaisesRegex(ValueError, "CIRCUIT BREAKER"):
            tool_use.run(llm, Mock())
        self.assertEqual(len(llm.calls), 1)

    def test_model_cannot_exceed_call_limit(self):
        llm = FakeLlm([response(calls=[("list_tables", "{}")] * 4)])
        with patch.object(tool_use, "dispatch", wraps=tool_use.dispatch) as dispatch:
            with self.assertRaisesRegex(ValueError, "tres llamadas"):
                tool_use.run(llm, Mock())
            self.assertEqual(dispatch.call_count, 3)

    def test_turn_and_time_limits(self):
        llm = FakeLlm([response(calls=[("list_tables", "{}")])] * 2)
        with patch.object(tool_use, "MAX_TURNS", 2), self.assertRaisesRegex(ValueError, "2 turnos"):
            tool_use.run(llm, Mock())
        timed = FakeLlm([])
        clock = Mock(side_effect=[0, 91])
        with self.assertRaisesRegex(ValueError, "TIMEOUT"):
            tool_use.run(timed, Mock(), clock=clock)
        self.assertFalse(timed.calls)

    def test_late_final_response_is_not_accepted(self):
        llm = FakeLlm([response("respuesta tardía")])
        with self.assertRaisesRegex(ValueError, "TIMEOUT"):
            tool_use.run(llm, Mock(), clock=Mock(side_effect=[0, 0, 91]))

    def test_refusal_does_not_replace_direct_permission_check(self):
        result = tool_use.run(FakeLlm([response("No puedo borrar pedidos.")]), Mock(), "destructivo")
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
