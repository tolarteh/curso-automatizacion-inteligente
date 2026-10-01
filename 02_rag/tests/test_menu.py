import importlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
menu = importlib.import_module("main")


class MenuTests(unittest.TestCase):
    def invoke(self, inputs, code=0):
        with patch("builtins.input", side_effect=inputs), \
             patch.object(menu.subprocess, "run", return_value=SimpleNamespace(returncode=code)) as run, \
             redirect_stdout(io.StringIO()) as output:
            result = menu.main()
        return result, run, output.getvalue()

    def test_exit_invalid_input_and_interruption_never_spawn(self):
        result, run, output = self.invoke(["x", "4", "0"])
        self.assertEqual(result, 0)
        run.assert_not_called()
        self.assertIn("Opción inválida", output)
        for failure, code in ((EOFError, 0), (KeyboardInterrupt, 130)):
            result, run, _ = self.invoke(failure)
            self.assertEqual(result, code)
            run.assert_not_called()

    def test_only_selected_script_runs_with_current_interpreter_and_exit_code(self):
        for option, (_, _, filename) in menu.LESSONS.items():
            result, run, _ = self.invoke([option], 2)
            self.assertEqual(result, 2)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], [sys.executable, str(menu.SOURCE / filename)])
            self.assertEqual(run.call_args.kwargs["cwd"], menu.TOPIC)
            self.assertEqual(run.call_args.kwargs["env"]["PYTHONUTF8"], "1")
            self.assertTrue((menu.SOURCE / filename).is_file())

    def test_spawn_error_is_visible(self):
        with patch("builtins.input", return_value="1"), \
             patch.object(menu.subprocess, "run", side_effect=OSError("fallo de prueba")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(menu.main(), 1)
            self.assertIn("ERROR", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
