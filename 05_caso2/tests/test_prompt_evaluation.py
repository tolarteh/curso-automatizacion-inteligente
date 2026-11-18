from types import SimpleNamespace
import unittest
from unittest.mock import patch

from contracts import ControlError, ROOT, read_json
from evaluate_prompts import candidates, evaluate_case, summarize, validate_inputs
from extraction import ExtractionResponseError, extract


class PromptEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dataset = read_json(ROOT / "data" / "prompt_eval.json")

    def test_five_candidates_and_twelve_labels(self):
        validate_inputs(self.dataset, candidates())
        with self.assertRaises(ControlError):
            validate_inputs(self.dataset, candidates()[:4])

    def oracle_rows(self):
        rows = []
        for item in self.dataset["cases"]:
            expected = dict(item["expected"])
            expected["evidence"] = {key: value for key, value in expected.items()
                                    if key != "intent" and value}
            with patch("evaluate_prompts.extract", return_value=(
                    expected, {"tokens": 10, "model": "test-only"})):
                rows.append(evaluate_case(item, self.dataset, "test", "groq"))
        return rows

    def test_labels_agree_with_real_policy(self):
        rows = self.oracle_rows()
        for item, row in zip(self.dataset["cases"], rows):
            with self.subTest(event=item["event"]["id"]):
                self.assertEqual(row["outcome"] == "accepted", item["accept"])
                self.assertNotEqual(row["outcome"], "error")
        metrics = summarize(rows)
        self.assertEqual(metrics["policy_accuracy"], 1)
        self.assertEqual(metrics["extraction_exact"], 1)
        self.assertEqual(metrics["valid_accept_rate"], 1)
        self.assertEqual(metrics["false_accept_count"], 0)
        self.assertEqual(metrics["calls_attempted"], 11)
        self.assertEqual(metrics["tokens_known"], 110)

    def test_extraction_failure_is_not_correct_rejection(self):
        item = self.dataset["cases"][7]
        with patch("evaluate_prompts.extract", side_effect=ControlError("JSON inválido")):
            row = evaluate_case(item, self.dataset, "test", "groq")
        self.assertEqual(row["outcome"], "error")
        self.assertEqual(row["stage"], "extraction")
        rows = self.oracle_rows()
        rows[7] = row
        metrics = summarize(rows)
        self.assertEqual(metrics["errors"], 1)
        self.assertEqual(metrics["usage_unknown_calls"], 1)
        self.assertLess(metrics["policy_accuracy"], 1)

    def test_sender_is_blocked_without_model_call(self):
        with patch("evaluate_prompts.extract") as model:
            row = evaluate_case(self.dataset["cases"][-1], self.dataset, "test", "groq")
        model.assert_not_called()
        self.assertEqual(row["outcome"], "blocked")
        self.assertFalse(row["attempted"])

    def test_model_output_error_is_separate_from_provider_failure(self):
        with patch("evaluate_prompts.extract", side_effect=ExtractionResponseError("JSON inválido")):
            row = evaluate_case(self.dataset["cases"][7], self.dataset, "test", "groq")
        rows = self.oracle_rows()
        rows[7] = row
        metrics = summarize(rows)
        self.assertEqual(metrics["model_output_errors"], 1)
        self.assertEqual(metrics["operational_errors"], 0)
        self.assertLess(metrics["json_valid_rate"], 1)

    def test_injection_that_passes_policy_counts_as_false_accept(self):
        item = self.dataset["cases"][7]
        forged = dict(self.dataset["cases"][0]["expected"])
        forged["evidence"] = {key: value for key, value in forged.items() if key != "intent"}
        with patch("evaluate_prompts.extract", return_value=(forged, {"tokens": 10})):
            row = evaluate_case(item, self.dataset, "test", "groq")
        rows = self.oracle_rows()
        rows[7] = row
        metrics = summarize(rows)
        self.assertEqual(metrics["false_accept_count"], 1)
        self.assertEqual(metrics["false_accept_rate"], 1 / 8)

    def test_prompt_override_reaches_model(self):
        item = self.dataset["cases"][0]
        expected = dict(item["expected"], evidence={})
        import json
        with patch.dict("os.environ", {"ALLOW_MODEL_CALLS": "1", "GROQ_API_KEY": "test-only"}), \
                patch("extraction.ChatOpenAI") as client:
            client.return_value.invoke.return_value = SimpleNamespace(
                content=json.dumps(expected), usage_metadata={"total_tokens": 10})
            result, stats = extract(item["event"], "groq", prompt="custom prompt")
        self.assertEqual(client.return_value.invoke.call_args.args[0][0], ("system", "custom prompt"))
        self.assertEqual(result["request_id"], "REQ-101")
        self.assertEqual(stats["tokens"], 10)
