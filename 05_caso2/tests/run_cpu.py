"""Pruebas CPU, sin modelo ni servicios externos."""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scaffold", action="store_true")
    parser.add_argument("--ci", action="store_true")
    args = parser.parse_args()
    pattern = "test_scaffold.py" if args.scaffold else "test_*.py"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.ci and not result.wasSuccessful():
        # El reto conserva fallos visibles. CI admite solo errores explícitos
        # de ejercicios pendientes, nunca fallos de controles o dependencias.
        pending = result.errors
        if not result.failures and pending and all(
            "NotImplementedError: TODO " in error for _, error in pending
        ):
            print(f"PENDIENTES: {len(pending)} contratos con TODO, no aprobados.")
            sys.exit(0)
    sys.exit(not result.wasSuccessful())
