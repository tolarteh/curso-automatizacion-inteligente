import json
import unittest

from contracts import ROOT, read_json
from extraction import Extraction, validate_evidence


class PromptTests(unittest.TestCase):
    def test_example_matches_output_contract_and_literal_evidence(self):
        prompt = (ROOT / "prompts" / "extract.txt").read_text(encoding="utf-8")
        examples = [line for line in prompt.splitlines() if line.startswith("{")]
        self.assertEqual(len(examples), 1)
        example = Extraction.model_validate(json.loads(examples[0])).model_dump()
        event = read_json(ROOT / "data" / "messages.json")[1]
        self.assertEqual(validate_evidence(event, example)["username"], "bruno.dev")
        self.assertIn('no objetos ni null', prompt)
        self.assertIn('evidence {}', prompt)
