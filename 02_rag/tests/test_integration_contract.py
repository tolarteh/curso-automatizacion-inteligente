import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
path = Path(__file__).resolve().parent / "integration" / "smoke_local.py"
spec = importlib.util.spec_from_file_location("rag_smoke", path)
if spec is None or spec.loader is None:
    raise RuntimeError("No se pudo cargar el runner de integración.")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class IntegrationContractTests(unittest.TestCase):
    def records(self, end, *, language=True, backend="local"):
        return [{"event": "run_start", "backend": backend}, {"event": "embedding_response"},
                *([{"event": "model_response"}] if language else []), {"event": "run_end", **end}]

    def test_opt_in_is_required_before_creating_clients(self):
        with patch.object(sys, "argv", ["smoke_local.py"]), patch.object(smoke, "OpenAI") as client:
            with self.assertRaises(SystemExit) as error:
                smoke.main()
            self.assertEqual(error.exception.code, 2)
            client.assert_not_called()

    def test_uncompleted_remote_and_wrong_role_answers_cannot_pass(self):
        end = {"completed": True, "status": "verificada", "respuesta": "Dato inventado",
               "searches": 1, "generations": 1}
        for records in (self.records({**end, "completed": False}), self.records(end, backend="groq"),
                        self.records(end)):
            with self.assertRaises(ValueError):
                smoke.validate_records("02_rag_avanzado", ["--pregunta", smoke.CUSTODY], records)

    def test_evaluation_requires_bounded_metrics_and_zero_protected_leaks(self):
        metrics = {"hit@1": 0.5, "hit@3": 0.7, "mrr@5": 0.6, "fugas": 0, "externos": 0}
        end = {"completed": True, "retrieval": {name: dict(metrics) for name in ("A", "B", "C", "D")}}
        smoke.validate_records("03_evaluacion", [], self.records(end, language=False))
        end["retrieval"]["B"]["fugas"] = 1
        with self.assertRaises(ValueError):
            smoke.validate_records("03_evaluacion", [], self.records(end, language=False))
        end["retrieval"]["B"]["fugas"] = 0
        end["retrieval"]["B"]["hit@1"] = True
        with self.assertRaises(ValueError):
            smoke.validate_records("03_evaluacion", [], self.records(end, language=False))


if __name__ == "__main__":
    unittest.main()
