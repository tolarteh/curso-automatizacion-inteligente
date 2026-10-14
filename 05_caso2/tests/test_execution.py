import copy
import shutil
import unittest
from contracts import ControlError, ROOT, Status, read_json, write_json
from execution import close_report, execute
from extraction import structured
from planning import approve, build_plan


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.output = ROOT / "outputs" / "tests" / self._testMethodName
        shutil.rmtree(self.output, ignore_errors=True)
        self.path = self.output / "inventory.json"
        inventory = read_json(ROOT / "data" / "inventory.json")
        write_json(self.path, inventory)
        request = structured(read_json(ROOT / "data" / "messages.json")[0]["body"])
        self.case = {"case_id": "synthetic", "status": Status.PENDING, "approvals": [],
                     "plan": build_plan(request, inventory), "journal": [], "pending_action": None}
        for actor, role in (("one", "manager"), ("two", "security")):
            approve(self.case, actor, role, "approve", self.case["plan"]["hash"], 1)

    def persist(self, case):
        write_json(self.output / "case.json", case)

    def test_verified_close(self):
        execute(self.case, self.path, self.persist)
        report = close_report(self.case, self.output)
        self.assertEqual(len(report["verified"]), 4)
        self.assertEqual(report["pending"], [])
        self.assertIn("PENDIENTES_MANUALES", report["status"])
        self.assertTrue(read_json(self.path)["users"]["ana.dev"]["blocked"])
        original = read_json(self.path)
        execute(self.case, self.path, self.persist)
        self.assertEqual(original, read_json(self.path))

    def test_partial_resume(self):
        with self.assertRaises(ControlError):
            execute(self.case, self.path, self.persist, fail_after=2)
        self.case = read_json(self.output / "case.json")
        self.assertEqual(self.case["status"], Status.PARTIAL)
        self.assertEqual(len(close_report(self.case, self.output)["pending"]), 2)
        execute(self.case, self.path, self.persist)
        self.assertEqual(self.case["status"], Status.DONE)

    def test_crash_reconcile(self):
        with self.assertRaises(ControlError):
            execute(self.case, self.path, self.persist, crash_after_change=1)
        self.case = read_json(self.output / "case.json")
        self.assertEqual(len(self.case["journal"]), 0)
        execute(self.case, self.path, self.persist)
        self.assertTrue(self.case["journal"][0]["reconciled"])
        self.assertEqual(len(self.case["journal"]), 4)

    def test_external_change(self):
        inventory = read_json(self.path)
        inventory["users"]["bruno.dev"]["teams"].append("new-team")
        write_json(self.path, inventory)
        with self.assertRaises(ControlError):
            execute(self.case, self.path, self.persist)
        self.assertEqual(self.case["status"], Status.STALE)
        self.assertEqual(self.case["approvals"], [])
        self.assertEqual(self.case["journal"], [])
        self.assertEqual(inventory, read_json(self.path))

    def test_tampered_plan(self):
        self.case["plan"]["actions"][0]["target"] = "other"
        original = read_json(self.path)
        with self.assertRaises(ControlError):
            execute(self.case, self.path, self.persist)
        self.assertEqual(original, read_json(self.path))
