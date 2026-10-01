import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import trace_log
from lesson_utils import evaluate_rows, expected, extract_sql, parse_json


class UtilsTests(unittest.TestCase):
    def test_strict_reference_and_types(self):
        self.assertTrue(evaluate_rows(expected()["por_region"])[0])
        for rows in ([], [{"region": "Cundinamarca", "retrasados": True}],
                     [{"region": "Cundinamarca", "retrasados": 5}] * 2,
                     [{"region": "Cundinamarca", "retrasados": 5, "extra": 1}]):
            self.assertFalse(evaluate_rows(rows)[0])

    def test_json_and_sql_parsing(self):
        self.assertEqual(parse_json('```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(extract_sql("```sql\nSELECT 1;\n```"), "SELECT 1")
        for text in (None, "", "comentario sin JSON", '{"ok": true} texto extra'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_json(text)

    def test_trace_masks_secrets_in_screen_and_file(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(trace_log, "TRACES", Path(directory)), \
                patch.dict(os.environ, {"GROQ_API_KEY": "clave-ficticia"}):
            trace = trace_log.Trace("prueba", "local", "modelo")
            trace.emit("dato", value="clave-ficticia")
            output = io.StringIO()
            with redirect_stdout(output):
                trace.show("Dato", "clave-ficticia")
                trace.end(completed=True)
            self.assertNotIn("clave-ficticia", output.getvalue())
            text = trace.path.read_text(encoding="utf-8")
            self.assertNotIn("clave-ficticia", text)
            records = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(records[-1]["event"], "run_end")
            self.assertIn("[SECRETO OCULTO]", text)


if __name__ == "__main__":
    unittest.main()
