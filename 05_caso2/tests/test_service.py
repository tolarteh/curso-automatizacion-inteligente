import shutil
import unittest
from unittest.mock import patch
from contracts import ControlError, ROOT, Status, read_json, write_json
import service
from tracking import Tracker


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.output = ROOT / "outputs" / "tests" / self._testMethodName
        shutil.rmtree(self.output, ignore_errors=True)
        self.output.mkdir(parents=True)
        uri = f"sqlite:///{(self.output / 'tracking.db').as_posix()}"
        self.patches = [
            patch.object(service, "OUTPUT", self.output),
            patch.object(service, "Tracker", lambda case_id, segment, level="metrics":
                         Tracker(case_id, segment, level, test_uri=uri)),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.event = read_json(ROOT / "data" / "messages.json")[0]

    def approved(self):
        case = service.ingest(self.event, "2026-10-14")
        for actor, role in (("one", "manager"), ("two", "security")):
            case = service.decide(case["case_id"], actor, role, "approve", case["plan"]["hash"], 1)
        return case

    def test_end_to_end_deterministic(self):
        case = self.approved()
        duplicate = service.ingest(self.event, "2026-10-14")
        self.assertEqual(duplicate["case_id"], case["case_id"])
        different_delivery = dict(self.event, id="another-mail")
        duplicate = service.ingest(different_delivery, "2026-10-14")
        self.assertEqual(duplicate["status"], "SOLICITUD_DUPLICADA")
        completed = service.run_execution(case["case_id"], "2026-10-14")
        self.assertEqual(completed["status"], Status.DONE)
        self.assertTrue((service.case_path(case["case_id"]).parent / "report.md").exists())

    def test_inventory_change_replan(self):
        case = self.approved()
        inventory = read_json(self.output / "git.json")
        inventory["revision"] += 1
        inventory["users"]["bruno.dev"]["teams"].append("changed")
        write_json(self.output / "git.json", inventory)
        with self.assertRaises(ControlError):
            service.run_execution(case["case_id"], "2026-10-14")
        revised = service.replan(case["case_id"], "2026-10-14")
        self.assertEqual(revised["plan"]["version"], 2)
        self.assertNotEqual(revised["plan"]["hash"], case["plan"]["hash"])
        self.assertEqual(revised["approvals"], [])
        with self.assertRaises(ControlError):
            service.decide(case["case_id"], "old", "manager", "approve", case["plan"]["hash"], 1)

    def test_tracking_failure_is_visible(self):
        with patch.object(service, "Tracker", side_effect=ControlError("Tracking no disponible")):
            with self.assertRaises(ControlError):
                service.ingest(self.event, "2026-10-14")
        case = service.load(service.digest(self.event["id"]))
        self.assertEqual(case["status"], Status.REJECTED)
        self.assertFalse((self.output / "git.json").exists())
