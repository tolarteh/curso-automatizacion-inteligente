from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from contracts import ControlError, ROOT, Status, digest, read_json, write_json
from extraction import structured
from main import demonstrate, main
from planning import approve, build_plan
import service


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.event = read_json(ROOT / "data" / "messages.json")[0]
        plan = build_plan(structured(self.event["body"]), read_json(ROOT / "data" / "inventory.json"))
        self.case = {"case_id": digest(self.event["id"]), "status": Status.PENDING, "plan": plan,
                     "approvals": [], "journal": [], "pending_action": None, "errors": []}
        self.path = self.output / "cases" / self.case["case_id"] / "case.json"
        self.stdout = StringIO()

    def run_demo(self, answers):
        with patch("builtins.input", side_effect=answers), patch.object(service, "OUTPUT", self.output):
            with redirect_stdout(self.stdout):
                demonstrate(self.event, "2026-10-14", "metrics")

    def test_saved_case_does_not_repeat_ingestion(self):
        write_json(self.path, self.case)
        with patch.object(service, "ingest") as ingest:
            self.run_demo(["0"])
        ingest.assert_not_called()

    def test_approval_uses_current_plan_without_execution(self):
        write_json(self.path, self.case)
        with patch.object(service, "decide") as decide, patch.object(service, "run_execution") as execute:
            self.run_demo(["1", "leader", "0"])
        decide.assert_called_once_with(self.case["case_id"], "leader", "manager", "approve",
                                       self.case["plan"]["hash"], 1, "metrics")
        execute.assert_not_called()

    def test_same_actor_attack_is_visible(self):
        approve(self.case, "leader", "manager", "approve", self.case["plan"]["hash"], 1)
        write_json(self.path, self.case)
        with patch.object(service, "decide", side_effect=ControlError("Actor o rol ya registrado.")) as decide:
            self.run_demo(["4", "0"])
        decide.assert_called_once_with(self.case["case_id"], "leader", "security", "approve",
                                       self.case["plan"]["hash"], 1, "metrics")
        self.assertIn("Actor o rol ya registrado.", self.stdout.getvalue())

    def test_partial_failure_is_explicit_and_can_resume(self):
        write_json(self.path, self.case)
        with patch.object(service, "run_execution",
                          side_effect=[ControlError("Fallo parcial"), self.case]) as execute:
            self.run_demo(["7", "si", "6", "si", "0"])
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args_list[0].kwargs["fail_after"], 2)
        self.assertIsNone(execute.call_args_list[1].kwargs["fail_after"])
        self.assertIn("Fallo parcial", self.stdout.getvalue())

    def test_old_hash_and_crash_arguments(self):
        approve(self.case, "leader", "manager", "approve", self.case["plan"]["hash"], 1)
        write_json(self.path, self.case)
        with patch.object(service, "decide") as decide, patch.object(service, "run_execution") as execute:
            self.run_demo(["5", "other", "8", "si", "0"])
        decide.assert_called_once_with(self.case["case_id"], "other", "security", "approve",
                                       "hash-viejo", 1, "metrics")
        self.assertEqual(execute.call_args.kwargs["crash_after_change"], 1)

    def test_main_opens_email_list_directly(self):
        with patch("events.fetch_events", return_value=[self.event]), \
                patch("builtins.input", return_value="0"), redirect_stdout(self.stdout):
            main()
        self.assertIn("mail-001: Formulario", self.stdout.getvalue())
        self.assertNotIn("Lección:", self.stdout.getvalue())

    def test_rejected_ingestion_shows_actual_error(self):
        def reject(*args):
            self.case.pop("plan")
            self.case["status"] = Status.REJECTED
            self.case["errors"] = ["ControlError"]
            write_json(self.path, self.case)
            raise ControlError("Remitente no permitido.")

        with patch.object(service, "ingest", side_effect=reject):
            self.run_demo(["si", ""])
        self.assertIn("Remitente no permitido.", self.stdout.getvalue())
        self.assertIn("Sin plan", self.stdout.getvalue())
