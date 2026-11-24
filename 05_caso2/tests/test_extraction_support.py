from types import SimpleNamespace
import unittest
from unittest.mock import patch

from contracts import ControlError, ROOT, read_json
from extraction import extract


class ExtractionSupportTests(unittest.TestCase):
    def test_non_json_and_wrong_schema_fail_closed(self):
        event = read_json(ROOT / "data" / "messages.json")[4]
        for content in ("I cannot comply.", '{"intent":"invalid","username":null}'):
            with self.subTest(content=content), patch.dict(
                "os.environ", {"ALLOW_MODEL_CALLS": "1", "GROQ_API_KEY": "test-only"}
            ), patch("extraction.ChatOpenAI") as client:
                client.return_value.invoke.return_value = SimpleNamespace(content=content)
                with self.assertRaisesRegex(ControlError, "fuera del contrato JSON"):
                    extract(event, "groq")
                client.return_value.invoke.assert_called_once()
