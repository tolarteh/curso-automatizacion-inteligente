"""Aceptación del reto, separada de las pruebas de la implementación completa."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from caso3.rag.indexar import indexar
from ejercicios import filter_rules, parse_amount, pass_power, request_revision


class ExerciseTests(unittest.TestCase):
    def test_amount(self):
        self.assertEqual(parse_amount("1.200.000"), Decimal("1200000"))
        with self.assertRaises(ValueError):
            parse_amount("sin valor")

    def test_dates(self):
        norms = {fragment.norma.fuente: fragment.norma for fragment in indexar()}
        rules = [dict(fuente=norm.fuente, vigente_desde=norm.vigente_desde,
                      vigente_hasta=norm.vigente_hasta) for norm in norms.values()]
        by_source = {rule["fuente"]: rule for rule in rules}
        self.assertEqual(filter_rules(rules, date(2026, 1, 1)), [by_source["circular-2026.md"]])
        self.assertEqual(filter_rules(rules, date(2025, 12, 31)), [by_source["manual-2024.md"]])

    def test_limit(self):
        self.assertEqual(request_revision(dict(vueltas=0))["vueltas"], 1)
        self.assertEqual(request_revision(dict(vueltas=1))["vueltas"], 2)
        with self.assertRaises(ValueError):
            request_revision(dict(vueltas=2))

    def test_metric(self):
        self.assertTrue(pass_power([True, True, True], 3))
        self.assertFalse(pass_power([True, False, True], 3))
        self.assertFalse(pass_power([True], 3))
        with self.assertRaises(ValueError):
            pass_power([], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
