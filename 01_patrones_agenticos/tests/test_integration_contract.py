from copy import deepcopy
from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parent / "integration" / "smoke_local.py"
spec = importlib.util.spec_from_file_location("smoke_local", path)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def records(**end):
    return [{"event": "run_start", "backend": "local"},
            {"event": "model_response"},
            {"event": "run_end", "completed": True, **end}]


class IntegrationContractTests(unittest.TestCase):
    def test_real_run_requires_explicit_flag(self):
        with patch.object(sys, "argv", ["smoke_local.py"]), \
                patch.object(smoke, "OpenAI") as client, redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as error:
                smoke.main()
            self.assertEqual(error.exception.code, 2)
            client.assert_not_called()
            self.assertIn("--run", errors.getvalue())

    def test_each_lesson_has_specific_pass_criteria(self):
        smoke.validate_records("01_reflection", records(last_passed=True, corrections=1))
        smoke.validate_records("02_tool_use", records(verified=True, tool_calls=2, case="normal"))
        smoke.validate_records("02_tool_use", records(verified=True, tool_calls=0, case="destructivo"))
        smoke.validate_records("03_planning", records(status="rejected", rows_verified=True, executed_steps=2))

    def test_old_failed_or_remote_evidence_cannot_pass(self):
        valid = records(last_passed=True, corrections=1)
        variants = [[], valid[:-1], valid + [valid[-1]], [valid[0], valid[-1]]]
        failed = deepcopy(valid)
        failed[-1]["completed"] = False
        remote = deepcopy(valid)
        remote[0]["backend"] = "groq"
        variants.extend([failed, remote, records(last_passed=False, corrections=2),
                         records(last_passed=True, corrections=3),
                         records(last_passed=True, corrections=True)])
        for value in variants:
            with self.subTest(records=value), self.assertRaises(ValueError):
                smoke.validate_records("01_reflection", value)


if __name__ == "__main__":
    unittest.main()
