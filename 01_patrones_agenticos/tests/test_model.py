import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import model
from openai import OpenAIError


class ModelTests(unittest.TestCase):
    def test_local_configuration_cannot_point_to_remote(self):
        with patch.dict(os.environ, {"LOCAL_BASE_URL": "https://example.invalid/v1"}):
            with self.assertRaisesRegex(ValueError, "esta máquina"):
                model.make_backend("local")

    def test_missing_key_and_invalid_backend_fail(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "GROQ_API_KEY"):
                model.make_backend("groq")
        with self.assertRaisesRegex(ValueError, "desconocido"):
            model.make_backend("automatico")

    def test_env_is_at_topic_root_and_process_has_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("LOCAL_MODEL=archivo\nLOCAL_REASONING_EFFORT=none\n", encoding="utf-8")
            with patch.object(model, "TOPIC", root), \
                    patch.dict(os.environ, {"LOCAL_MODEL": "proceso"}, clear=True):
                model.load_local_env()
                self.assertEqual(os.environ["LOCAL_MODEL"], "proceso")
                self.assertEqual(os.environ["LOCAL_REASONING_EFFORT"], "none")

    def test_sdk_errors_stop_without_retry_or_switch(self):
        trace = Mock()
        with patch("model.OpenAI") as constructor:
            client = constructor.return_value
            client.chat.completions.create.side_effect = OpenAIError("fallo de prueba")
            llm = model.Llm(model.Backend("local", "http://localhost:1234/v1", "demo-local", "local", None), trace)
            with self.assertRaises(SystemExit) as error:
                llm.chat([], purpose="prueba")
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(client.chat.completions.create.call_count, 1)
            self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)
            trace.end.assert_called_once_with(completed=False, reason="error del modelo")

    def test_truncation_is_explicit_and_programming_errors_propagate(self):
        with patch("model.OpenAI") as constructor:
            llm = model.Llm(model.Backend("local", "http://localhost:1234/v1", "demo-local", "local", None), Mock())
            client = constructor.return_value.chat.completions
            client.create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")])
            with self.assertRaisesRegex(ValueError, "incompleta"):
                llm.chat([], purpose="prueba")
            client.create.side_effect = ValueError("bug")
            with self.assertRaisesRegex(ValueError, "bug"):
                llm.chat([], purpose="prueba")


if __name__ == "__main__":
    unittest.main()
