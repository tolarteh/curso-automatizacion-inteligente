import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seed import expected_result, is_late, seed_database
from settings import CUTOFF, EXPECTED


class DataTests(unittest.TestCase):
    def test_reference_is_independent_and_exact(self):
        self.assertEqual(expected_result(), json.loads(EXPECTED.read_text(encoding="utf-8")))
        self.assertEqual(expected_result()["total_retrasados"], 11)

    def test_boundary_null_and_cancelled(self):
        self.assertTrue(is_late("2026-03-31 15:00", "2026-04-02 10:00", "entregado"))
        self.assertTrue(is_late("2026-03-18 10:00", None, "en_transito"))
        self.assertFalse(is_late("2026-03-18 10:00", None, "cancelado"))
        self.assertFalse(is_late("2026-02-25 10:00", "2026-03-03 15:00", "entregado"))
        self.assertFalse(is_late("2026-03-26 10:00", "2026-03-26 10:00", "entregado"))

    def test_seed_and_safe_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "demo.sqlite"
            seed_database(database)
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 26)
            with self.assertRaises(FileExistsError):
                seed_database(database)
            seed_database(database, reset=True)

    def test_never_replaces_an_unmarked_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "foreign.sqlite"
            with closing(sqlite3.connect(database)) as db:
                db.execute("CREATE TABLE important (value TEXT)")
            before = database.read_bytes()
            with self.assertRaises(ValueError):
                seed_database(database, reset=True)
            self.assertEqual(database.read_bytes(), before)

    def test_snapshot_includes_pending_orders_without_future_deliveries(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "demo.sqlite"
            seed_database(database)
            with closing(sqlite3.connect(database)) as db:
                future = db.execute(
                    "SELECT COUNT(*) FROM orders WHERE delivered_at >= ?", (CUTOFF,)
                ).fetchone()[0]
                pending = db.execute(
                    "SELECT COUNT(*) FROM orders WHERE delivered_at IS NULL AND status != 'cancelado'"
                ).fetchone()[0]
            self.assertEqual(future, 0)
            self.assertGreater(pending, 0)


if __name__ == "__main__":
    unittest.main()
