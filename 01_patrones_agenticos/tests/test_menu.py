import importlib
import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
menu = importlib.import_module("main")


class MenuTests(unittest.TestCase):
    def call_menu(self, inputs, returncode=0):
        output = io.StringIO()
        with patch("builtins.input", side_effect=inputs), \
                patch.object(menu.subprocess, "run", return_value=SimpleNamespace(returncode=returncode)) as run, \
                redirect_stdout(output):
            result = menu.main()
        return result, run, output.getvalue()

    def test_exit_and_invalid_input_do_not_execute(self):
        result, run, output = self.call_menu(["x", "8", "0"])
        self.assertEqual(result, 0)
        run.assert_not_called()
        self.assertIn("Opción inválida", output)
        for failure, code in ((EOFError, 0), (KeyboardInterrupt, 130)):
            result, run, _ = self.call_menu(failure)
            self.assertEqual(result, code)
            run.assert_not_called()

    def test_each_option_resolves_script_and_preserves_exit_code(self):
        for option, (_, _, filename) in menu.LESSONS.items():
            with self.subTest(option=option):
                result, run, _ = self.call_menu([option], returncode=2)
                self.assertEqual(result, 2)
                self.assertEqual(run.call_args.args[0], [sys.executable, str(menu.SOURCE / filename)])
                self.assertEqual(run.call_args.kwargs["cwd"], menu.TOPIC)
                self.assertTrue((menu.SOURCE / filename).is_file())

    def test_spawn_errors_are_reported(self):
        with patch("builtins.input", return_value="1"), \
                patch.object(menu.subprocess, "run", side_effect=OSError("fallo de prueba")), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(menu.main(), 1)
            self.assertIn("ERROR", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
