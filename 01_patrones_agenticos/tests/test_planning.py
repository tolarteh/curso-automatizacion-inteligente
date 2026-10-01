from copy import deepcopy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import FakeLlm, response
from seed import seed_database
from sql_readonly import QueryRejected, run_sql_readonly
from test_plan_contract import PLAN

planning = importlib.import_module("03_planning")


class PlanningTests(unittest.TestCase):
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

        patcher = patch.object(planning, "safe_run", safe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_approval_and_rejection_are_explicit_without_sending(self):
        for approved in (True, False):
            approve = Mock(return_value=approved)
            llm = FakeLlm([response(json.dumps(PLAN)), response("11 retrasados; Cundinamarca 5.")])
            result = planning.run(llm, Mock(), approve)
            self.assertEqual(result["status"], "approved" if approved else "rejected")
            self.assertEqual(result["executed_steps"], 2)
            self.assertTrue(result["rows_verified"])
            approve.assert_called_once_with(PLAN["pasos"][-1])

    def test_invalid_plan_never_executes(self):
        with patch.object(planning, "safe_run") as safe:
            with self.assertRaisesRegex(ValueError, "Plan rechazado"):
                planning.run(FakeLlm([response("{}")]), Mock(), Mock())
            safe.assert_not_called()

    def test_high_risk_requires_approval_before_sql(self):
        plan = deepcopy(PLAN)
        plan["pasos"][0]["riesgo"] = "alto"
        with patch.object(planning, "safe_run") as safe:
            result = planning.run(FakeLlm([response(json.dumps(plan))]), Mock(), Mock(return_value=False))
            self.assertEqual(result["executed_steps"], 0)
            safe.assert_not_called()

    def test_software_without_tool_stops_before_any_step(self):
        plan = deepcopy(PLAN)
        plan["pasos"][1]["ejecutor"] = "software"
        llm = FakeLlm([response(json.dumps(plan))])
        approve = Mock()
        with patch.object(planning, "safe_run") as safe:
            with self.assertRaisesRegex(ValueError, "software necesita una herramienta"):
                planning.run(llm, Mock(), approve)
            safe.assert_not_called()
        approve.assert_not_called()
        self.assertEqual(len(llm.calls), 1)

    def test_wrong_counts_stop_before_summary_and_human(self):
        plan = deepcopy(PLAN)
        plan["pasos"][0]["sql"] = "SELECT 'Antioquia' AS region, 1 AS retrasados"
        approve = Mock()
        with self.assertRaises(AssertionError):
            planning.run(FakeLlm([response(json.dumps(plan))]), Mock(), approve)
        approve.assert_not_called()

    def test_no_stdin_means_rejection(self):
        for failure in (EOFError, KeyboardInterrupt):
            with patch("builtins.input", side_effect=failure):
                self.assertFalse(planning.ask_approval(Mock(), PLAN["pasos"][-1], None))


if __name__ == "__main__":
    unittest.main()
