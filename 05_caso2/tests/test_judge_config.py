from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import openai


SCRIPT = Path(__file__).resolve().parents[1] / "evals" / "judge.py"


class JudgeConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        script_dir = self.root / "evals"
        script_dir.mkdir()
        self.script = script_dir / "judge.py"
        shutil.copyfile(SCRIPT, self.script)
        self.dataset = script_dir / "sample.jsonl"
        self.dataset.write_text(json.dumps({
            "id": "test-01", "category": "normal", "body": "Solicitud sintética",
            "expected": {"outcome": "advance"},
        }) + "\n", encoding="utf-8")

    def run_script(self, client, mode="judge"):
        content = '{"verdict":"advance","reason":"Válida"}' if mode == "judge" else "0.1"
        client.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
        with patch("sys.argv", [
            str(self.script), "--mode", mode, "--dataset", str(self.dataset),
        ]), patch("time.sleep"), redirect_stdout(io.StringIO()):
            runpy.run_path(str(self.script), run_name="__main__")

    def test_loads_local_env_for_both_modes(self):
        (self.root / ".env").write_text(
            "GROQ_API_KEY=test-local\nJUDGE_MODEL=test-model\n", encoding="utf-8",
        )
        for mode in ("judge", "guard"):
            with self.subTest(mode=mode), patch.dict(os.environ, {}, clear=True), \
                    patch.object(openai, "OpenAI") as client:
                self.run_script(client, mode)
                client.assert_called_once_with(
                    api_key="test-local", base_url="https://api.groq.com/openai/v1",
                )
                expected = "test-model" if mode == "judge" else "meta-llama/llama-prompt-guard-2-86m"
                self.assertEqual(
                    client.return_value.chat.completions.create.call_args.kwargs["model"],
                    expected,
                )

    def test_process_key_takes_priority(self):
        (self.root / ".env").write_text("GROQ_API_KEY=test-local\n", encoding="utf-8")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-process"}, clear=True), \
                patch.object(openai, "OpenAI") as client:
            self.run_script(client)
            self.assertEqual(client.call_args.kwargs["api_key"], "test-process")

    def test_missing_or_blank_key_reports_actionable_error(self):
        for env in ({}, {"GROQ_API_KEY": ""}, {"GROQ_API_KEY": "  "}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True), \
                    patch.object(openai, "OpenAI") as client, redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as raised:
                    self.run_script(client)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("Falta GROQ_API_KEY", error.getvalue())
                self.assertIn(str(self.root / ".env"), error.getvalue())
                client.assert_not_called()
