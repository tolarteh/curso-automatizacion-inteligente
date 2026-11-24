"""Serialización sin pérdida en las fronteras entre agentes."""
from datetime import date
from decimal import Decimal
import unittest

from pydantic import ValidationError

from caso3.contratos import (
    Clasificacion, Dictamen, Documento, Extraccion, Extracciones, Hallazgo,
    Hallazgos, Item, Paso, ReglaCitada, Reglas, Traza,
)


class ContractTests(unittest.TestCase):
    def test_roundtrip_every_contract(self):
        document = Documento(id="factura", tipo="factura", ruta="factura.txt", texto="Sintético")
        item = Item(descripcion="Sensor", cantidad=2, valor_unitario=Decimal("100.01"))
        extraction = Extraccion(
            doc_id=document.id, nit="900123456", monto_total=Decimal("200.02"),
            iva_incluido=True, fecha=date(2026, 6, 1), items=[item], es_ganadora=False,
        )
        rule = ReglaCitada(
            fuente="circular-2026.md", version="2026", vigente_desde=date(2026, 1, 1),
            texto="Norma sintética.",
        )
        finding = Hallazgo(codigo="MONTO", severidad="bloqueante", detalle="Difiere", regla=rule)
        verdict = Dictamen(decision="devolver", hallazgos=[finding], reglas=[rule], vueltas=2)
        step = Paso(agente="extractor", entrada_resumen="1 documento", salida_resumen="1 monto", ms=1)
        values = [
            document, item, extraction, rule, finding, verdict, step,
            Clasificacion(documentos=[document], faltantes=[]),
            Extracciones(extracciones=[extraction]), Reglas(reglas=[rule]),
            Hallazgos(hallazgos=[finding]),
            Traza(expediente_id="E01", pasos=[step], vueltas=2),
        ]
        for value in values:
            with self.subTest(contract=type(value).__name__):
                self.assertEqual(value, type(value).model_validate_json(value.model_dump_json()))
        self.assertIsInstance(extraction.monto_total, Decimal)
        self.assertEqual(extraction.fecha, date(2026, 6, 1))

    def test_reject_unsafe_handoffs(self):
        payload = dict(
            doc_id="factura", nit="900123456", monto_total="200.02", iva_incluido=None,
            fecha="2026-06-01", items=[], es_ganadora=False,
        )
        for overrides in ({"monto_total": 200.02}, {"fecha": "01/06/2026"}, {"monto_total": "NaN"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                Extraccion(**(payload | overrides))
        for overrides in ({"vueltas": 3}, {"requiere_firma": False}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                Dictamen(**(dict(decision="aprobar", hallazgos=[], reglas=[], vueltas=0) | overrides))
