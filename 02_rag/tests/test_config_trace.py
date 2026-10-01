import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import model_config
import trace_log


class ConfigTraceTests(unittest.TestCase):
    def test_configuration_is_local_and_process_has_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            topic = Path(directory)
            (topic / ".env").write_text("LOCAL_MODEL=archivo\n", encoding="utf-8")
            with patch.object(model_config, "TOPIC", topic), patch.dict(os.environ, {"LOCAL_MODEL": "proceso"}):
                model_config.load_local_env()
                self.assertEqual(model_config.make_backend("local").model, "proceso")

    def test_local_endpoint_and_remote_key_are_validated(self):
        for url in ("https://example.com/v1", "http://localhost.example.com/v1",
                    "http://user:pass@localhost/v1", "http://localhost/v1?key=value"):
            with self.assertRaises(ValueError):
                model_config.local_url(url)
        self.assertEqual(model_config.local_url("http://127.0.0.1:1234/v1"), "http://127.0.0.1:1234/v1")
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(ValueError):
                model_config.make_backend("groq")
        with self.assertRaises(ValueError):
            model_config.make_backend("desconocido")

    def test_trace_masks_secrets_on_screen_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = io.StringIO()
            with patch.object(trace_log, "TRACES", Path(directory)), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "clave-privada-de-prueba"}), redirect_stdout(screen):
                trace = trace_log.Trace("prueba", "local", "demo-local")
                trace.show("clave-privada-de-prueba", "clave-privada-de-prueba")
                trace.end(completed=True)
            content = trace.path.read_text(encoding="utf-8")
            self.assertNotIn("clave-privada-de-prueba", content + screen.getvalue())
            self.assertEqual(json.loads(content.splitlines()[-1])["completed"], True)


if __name__ == "__main__":
    unittest.main()
