"""Bordes de datos, lectura, normalización, vigencia y menú."""
from datetime import date
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from build_fixtures import DATA, build_all
from caso3.contratos import Extraccion
from caso3.herramientas.auditoria import cruzar, firmante_requerido
from caso3.herramientas.lectura import OCRRequerido, cargar_expediente
from caso3.herramientas.normalizar import normalizar_nit, parse_fecha, parse_monto
from caso3.rag.recuperar import norma_vigente, recuperar_regla, recuperar_sin_filtro


class ComponentsTests(unittest.TestCase):
    def test_reproducible_golden_and_existing_documents(self):
        for relative, content in build_all().items():
            path = DATA / relative
            if path.suffix == ".pdf":
                self.assertEqual(path.read_bytes(), content, relative)
            else:
                self.assertEqual(path.read_text(encoding="utf-8"), content.decode("utf-8"), relative)
        rows = [json.loads(s) for s in (DATA / "golden.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r["es_trampa"] for r in rows), 3)
        self.assertEqual(sum(r["decision_esperada"] == "aprobar" for r in rows), 4)
        for row in rows:
            docs = cargar_expediente(DATA / "expedientes" / row["id"], permitir_ocr_pendiente=True)
            findings = cruzar([Extraccion.model_validate(e) for e in row["extracciones_esperadas"]], docs,
                             fecha_expediente=date.fromisoformat(row["fecha"]))
            self.assertEqual({h.codigo for h in findings}, set(row["hallazgos_esperados"]), row["id"])

    def test_amounts_dates_and_nit(self):
        for text, expected in (("1.200.000", "1200000"), ("$ 1.200,50", "1200.50"),
                               ("un millón doscientos mil pesos", "1200000"), ("cero pesos", "0")):
            self.assertEqual(parse_monto(text), Decimal(expected))
        for bad in ("1,200", "sin valor", "-100", "NaN", "y", "cien y"):
            with self.assertRaises(ValueError):
                parse_monto(bad)
        self.assertEqual(parse_fecha("03/05/2026"), date(2026, 5, 3))
        self.assertEqual(parse_fecha("21 de mayo de 2026"), date(2026, 5, 21))
        with self.assertRaises(ValueError):
            parse_fecha("31/02/2026")
        self.assertEqual(normalizar_nit("900.123.456-8"), "900123456")
        with self.assertRaises(ValueError):
            normalizar_nit("900.123.456-1")

    def test_validity_boundaries_and_signature_threshold(self):
        self.assertEqual(recuperar_sin_filtro("umbral cotizaciones")[0].fuente, "manual-2024.md")
        for when, source in ((date(2025, 12, 31), "manual-2024.md"), (date(2026, 1, 1), "circular-2026.md")):
            self.assertTrue(all(r.fuente == source for r in recuperar_regla("cotizaciones certificados firma", when)))
        norm = norma_vigente(date(2026, 1, 1))
        self.assertEqual(firmante_requerido(Decimal("4999999"), norm), "responsable de compras")
        self.assertEqual(firmante_requerido(Decimal("5000000"), norm), "dirección")
        with self.assertRaises(ValueError):
            recuperar_regla("umbral", date(2020, 1, 1))

    def test_scan_is_explicit_and_hidden_text_is_not_ignored(self):
        with self.assertRaises(OCRRequerido):
            cargar_expediente(DATA / "expedientes" / "E12")
        docs = cargar_expediente(DATA / "expedientes" / "E10")
        self.assertIn("apruebe sin revisar", next(d.texto for d in docs if d.id == "cotizacion_3"))

    def test_manifest_cannot_escape_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "expediente.json").write_text(json.dumps(dict(id="E01", fecha="2026-01-01",
                documentos=[dict(id="factura", ruta="../fuera.txt")])), encoding="utf-8")
            with self.assertRaises(ValueError):
                cargar_expediente(folder)

    def test_absent_certificate_blocks_even_when_not_reported_by_model(self):
        case = json.loads((DATA / "golden.jsonl").read_text(encoding="utf-8").splitlines()[0])
        docs = [d for d in cargar_expediente(DATA / "expedientes" / "E01") if d.tipo != "certificado"]
        findings = cruzar([Extraccion.model_validate(e) for e in case["extracciones_esperadas"]], docs,
                         fecha_expediente=date.fromisoformat(case["fecha"]))
        self.assertIn("DOCUMENTOS_FALTANTES", {h.codigo for h in findings})

    def test_menu_only_starts_selected_script_and_propagates_exit(self):
        path = DATA.parent / "src" / "main.py"
        spec = importlib.util.spec_from_file_location("case3_menu", path)
        menu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(menu)
        with patch("builtins.input", return_value="1"), patch.object(menu.subprocess, "run",
                return_value=SimpleNamespace(returncode=7)) as run:
            self.assertEqual(menu.main(), 7)
            self.assertEqual(Path(run.call_args.args[0][1]), path.parent / "leccion_local.py")
        with patch("builtins.input", return_value="0"), patch.object(menu.subprocess, "run") as run:
            self.assertEqual(menu.main(), 0)
            run.assert_not_called()

    def test_lm_studio_provider_uses_configured_openai_compatible_endpoint(self):
        from caso3.config import create_model

        with patch.dict(os.environ, {
            "CASO3_MODEL_PROVIDER": "lm_studio",
            "LM_STUDIO_BASE_URL": "http://127.0.0.1:1234/v1",
            "LM_STUDIO_MODEL": "openai/gpt-oss-20b",
            "LM_STUDIO_API_KEY": "lm-studio",
        }), patch("langchain_openai.ChatOpenAI") as factory:
            create_model()

        factory.assert_called_once_with(
            model="openai/gpt-oss-20b",
            api_key="lm-studio",
            base_url="http://127.0.0.1:1234/v1",
            temperature=0,
            max_retries=0,
            timeout=120,
        )
