import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fakes import CORRECT_SQL, FakeLlm, response
from seed import seed_database
from sql_readonly import run_sql_readonly

reflection = importlib.import_module("01_reflection")


class ReflectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        database = Path(self.directory.name) / "demo.sqlite"
        seed_database(database)
        self.patch = patch.object(reflection, "run_sql_readonly",
                                  lambda sql: run_sql_readonly(sql, database))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_improvement_with_exact_reference(self):
        llm = FakeLlm([response("SELECT 'Antioquia' AS region, 1 AS retrasados"),
                       response('{"cumple": false, "problemas": ["faltan regiones"]}'),
                       response(CORRECT_SQL), response('{"cumple": true, "problemas": []}')])
        result = reflection.run(llm, Mock())
        self.assertFalse(result["first_passed"])
        self.assertTrue(result["last_passed"])
        self.assertEqual(result["corrections"], 1)

    def test_critic_cannot_approve_wrong_counts(self):
        llm = FakeLlm([response("SELECT 'Antioquia' AS region, 1 AS retrasados"),
                       response('{"cumple": true, "problemas": []}')])
        with self.assertRaises(AssertionError):
            reflection.run(llm, Mock())

    def test_invalid_critique_is_not_a_success(self):
        for critique in ({"cumple": "true", "problemas": []},
                         {"cumple": True, "problemas": ["error"]},
                         {"cumple": False, "problemas": [1]}, {}):
            with self.subTest(critique=critique), self.assertRaises(ValueError):
                reflection.validate_critique(critique)

    def test_two_rounds_are_a_hard_limit(self):
        bad = "SELECT 'Antioquia' AS region, 1 AS retrasados"
        llm = FakeLlm([response(bad), response('{"cumple": false, "problemas": ["error"]}'),
                       response(bad), response('{"cumple": false, "problemas": ["error"]}'), response(bad)])
        with self.assertRaises(AssertionError):
            reflection.run(llm, Mock())
        self.assertEqual(len(llm.calls), 5)


if __name__ == "__main__":
    unittest.main()
