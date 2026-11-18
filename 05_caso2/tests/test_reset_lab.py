from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from contracts import ControlError
import reset_lab
import service


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        for name in reset_lab.TARGETS:
            path = self.output / name
            if name == "cases":
                path.mkdir()
                (path / "case.json").write_text("{}")
            else:
                path.write_text("synthetic")
        (self.output / "mlflow").mkdir()
        (self.output / "mlflow" / "auth.ini").write_text("preserve")

    def run_reset(self):
        with patch.object(reset_lab, "OUTPUT", self.output), patch.object(service, "OUTPUT", self.output):
            with redirect_stdout(StringIO()):
                reset_lab.reset_state()

    def test_reset_preserves_mlflow_and_is_repeatable(self):
        self.run_reset()
        self.run_reset()
        self.assertTrue(all(not (self.output / name).exists() for name in reset_lab.TARGETS))
        self.assertEqual((self.output / "mlflow" / "auth.ini").read_text(), "preserve")
        self.assertFalse((self.output / "writer.lock").exists())

    def test_active_writer_blocks_deletion(self):
        (self.output / "writer.lock").write_text("")
        with self.assertRaises(ControlError):
            self.run_reset()
        self.assertTrue((self.output / "cases" / "case.json").exists())

    def test_unexpected_directory_blocks_deletion(self):
        path = self.output / "git.json"
        path.unlink()
        path.mkdir()
        with self.assertRaises(ControlError):
            self.run_reset()
        self.assertTrue((self.output / "cases" / "case.json").exists())

    def test_confirmation_is_required(self):
        with patch("builtins.input", return_value="no"), patch.object(reset_lab, "reset_state") as reset:
            with redirect_stdout(StringIO()):
                reset_lab.main()
        reset.assert_not_called()
