from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openai import OpenAIError
from model import Llm
from model_config import make_backend


def response(text="respuesta", finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=text), finish_reason=finish)])


class ModelTests(unittest.TestCase):
    def test_sdk_is_explicit_and_records_the_real_response(self):
        trace = Mock()
        with patch("model.OpenAI") as factory:
            llm = Llm(make_backend("local"), trace)
            factory.return_value.chat.completions.create.return_value = response()
            self.assertEqual(llm.chat([], purpose="prueba"), "respuesta")
            self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
            trace.emit.assert_called_once()

    def test_errors_stop_without_retry_or_fallback(self):
        trace = Mock()
        with patch("model.OpenAI") as factory:
            llm = Llm(make_backend("local"), trace)
            create = factory.return_value.chat.completions.create
            create.side_effect = OpenAIError("servidor no disponible")
            with self.assertRaises(SystemExit) as error:
                llm.chat([], purpose="prueba")
            self.assertEqual(error.exception.code, 2)
            create.assert_called_once()
            trace.end.assert_called_once_with(completed=False, reason="error del modelo")

    def test_empty_truncated_and_non_object_outputs_are_errors(self):
        with patch("model.OpenAI") as factory:
            llm = Llm(make_backend("local"), Mock())
            create = factory.return_value.chat.completions.create
            for value in (response(None), response(""), response("parcial", "length"),
                          SimpleNamespace(choices=[])):
                create.return_value = value
                with self.assertRaises(ValueError):
                    llm.chat([], purpose="prueba")
            create.return_value = response("[]")
            with self.assertRaises(ValueError):
                llm.chat_json([], {}, name="salida", purpose="prueba")
            create.return_value = response('{"ok":true}')
            self.assertEqual(llm.chat_json([], {}, name="salida", purpose="prueba"), {"ok": True})

    def test_truncated_response_is_traced_but_never_accepted(self):
        trace = Mock()
        with patch("model.OpenAI") as factory:
            llm = Llm(make_backend("local"), trace)
            factory.return_value.chat.completions.create.return_value = response("texto cortado", "length")
            with self.assertRaisesRegex(ValueError, "incompleta"):
                llm.chat([], purpose="prueba")
            self.assertEqual(trace.emit.call_args.kwargs["finish_reason"], "length")
            self.assertEqual(trace.emit.call_args.kwargs["content"], "texto cortado")


if __name__ == "__main__":
    unittest.main()
