import copy
from pathlib import Path
import unittest
from contracts import ControlError, ROOT, Status, read_json
from events import EventLedger
from extraction import extract, structured, validate_evidence
from unittest.mock import patch
from planning import approve, build_plan, ensure_authorized, validate_request


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.event = read_json(ROOT / "data" / "messages.json")[0]
        self.request = structured(self.event["body"])
        self.inventory = read_json(ROOT / "data" / "inventory.json")
        self.personnel = read_json(ROOT / "data" / "personnel.json")

    def case(self):
        return {"status": Status.PENDING, "plan": build_plan(self.request, self.inventory), "approvals": []}

    def test_event_identity(self):
        path = ROOT / "outputs" / "tests" / "event-test.sqlite"
        path.unlink(missing_ok=True)
        ledger = EventLedger(path)
        self.assertTrue(ledger.accept(self.event))
        self.assertFalse(ledger.accept(self.event))
        corrected = dict(self.event, body=self.event["body"] + "\n")
        with self.assertRaises(ControlError):
            ledger.accept(corrected)
        corrected["id"] = "new-id"
        self.assertTrue(ledger.accept(corrected))

    def test_evidence(self):
        self.assertEqual(validate_evidence(self.event, self.request)["username"], "ana.dev")
        for key in ("username", "employee_id", "request_id", "effective_date"):
            wrong = copy.deepcopy(self.request)
            wrong[key] = "inventado"
            with self.assertRaises(ControlError):
                validate_evidence(self.event, wrong)
        for intent in ("irrelevant", "invalid", "approve"):
            with self.assertRaises(ControlError):
                validate_evidence(self.event, dict(self.request, intent=intent))

    def test_sender(self):
        with self.assertRaises(ControlError):
            validate_evidence(dict(self.event, sender="evil@example.test"), self.request)

    def test_evidence_requires_matching_literal(self):
        for field in self.request["evidence"]:
            for invalid in ("missing", "empty", "blank", "different", "invented"):
                with self.subTest(field=field, invalid=invalid):
                    wrong = copy.deepcopy(self.request)
                    if invalid == "missing":
                        del wrong["evidence"][field]
                    elif invalid == "different":
                        wrong["evidence"][field] = "otra evidencia"
                    else:
                        value = {"empty": "", "blank": " ", "invented": "inventado"}[invalid]
                        wrong[field] = value
                        wrong["evidence"][field] = value
                    with self.assertRaises(ControlError):
                        validate_evidence(self.event, wrong)

    def test_registry_and_clock(self):
        validate_request(self.request, self.personnel, "2026-10-14")
        with self.assertRaises(ControlError):
            validate_request(self.request, self.personnel, "2026-10-13")
        with self.assertRaises(ControlError):
            validate_request(dict(self.request, username="bruno.dev"), self.personnel, "2026-10-14")

    def test_visibility(self):
        with self.assertRaises(ControlError):
            build_plan(self.request, dict(self.inventory, complete=False))

    def test_missing_and_duplicate_fields(self):
        with self.assertRaises(ControlError):
            structured("BAJA\nrequest_id=REQ-001")
        with self.assertRaises(ControlError):
            structured(self.event["body"] + "\nusername=other")

    def test_model_calls_are_opt_in(self):
        event = read_json(ROOT / "data" / "messages.json")[1]
        with patch.dict("os.environ", {"ALLOW_MODEL_CALLS": "0"}):
            with self.assertRaises(ControlError):
                extract(event)

    def test_injection_cannot_authorize(self):
        event = read_json(ROOT / "data" / "messages.json")[4]
        # Salida de extracción adversarial, solo prueba CPU, no modelo simulado.
        forged = dict(self.request, evidence=self.request["evidence"])
        with self.assertRaises(ControlError):
            validate_evidence(event, forged)

    def test_approvals(self):
        case = self.case()
        plan = case["plan"]
        with self.assertRaises(ControlError):
            ensure_authorized(case)
        approve(case, "manager-a", "manager", "approve", plan["hash"], 1)
        with self.assertRaises(ControlError):
            ensure_authorized(case)
        for actor, role, hash_value, version in (
            ("manager-a", "security", plan["hash"], 1),
            ("manager-b", "manager", plan["hash"], 1),
            ("security-a", "security", "old", 1),
            ("security-a", "security", plan["hash"], 0),
        ):
            with self.assertRaises(ControlError):
                approve(case, actor, role, "approve", hash_value, version)
        approve(case, "security-a", "security", "approve", plan["hash"], 1)
        ensure_authorized(case)
        case["plan"]["version"] = 2
        with self.assertRaises(ControlError):
            ensure_authorized(case)

    def test_rejection(self):
        case = self.case()
        approve(case, "manager-a", "manager", "reject", case["plan"]["hash"], 1)
        self.assertEqual(case["status"], Status.REJECTED)
        with self.assertRaises(ControlError):
            ensure_authorized(case)
