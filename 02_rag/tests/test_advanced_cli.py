from contextlib import redirect_stdout
import importlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
advanced = importlib.import_module("02_rag_avanzado")


class AdvancedCliTests(unittest.TestCase):
    def args(self, drawing=False):
        return SimpleNamespace(grafo=drawing, k=6, reindexar=False, rol="analista", pregunta="consulta")

    def test_blocked_execution_is_not_reported_as_success(self):
        backend = SimpleNamespace(name="local", model="demo-local")
        final = {"path": ["bloquear"], "status": "bloqueada", "answer": None,
                 "searches": 1, "generations": 2, "relevant": []}
        with patch.object(advanced, "start", return_value=(self.args(), backend)), \
             patch.object(advanced, "Trace") as trace, patch.object(advanced, "Llm"), \
             patch.object(advanced, "Embedder"), patch.object(advanced.Index, "build"), \
             patch.object(advanced, "run", return_value=final):
            self.assertEqual(advanced.main(), 2)
            self.assertFalse(trace.return_value.end.call_args.kwargs["completed"])
            self.assertIsNone(trace.return_value.end.call_args.kwargs["respuesta"])

    def test_graph_inspection_never_creates_model_clients(self):
        with patch.object(advanced, "start", return_value=(self.args(True), None)), \
             patch.object(advanced, "Llm") as llm, patch.object(advanced, "Embedder") as embedder, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(advanced.main(), 0)
            self.assertIn("calificar", output.getvalue())
            llm.assert_not_called()
            embedder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
