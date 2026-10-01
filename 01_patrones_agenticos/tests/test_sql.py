import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from seed import seed_database
from settings import EXPECTED
from sql_readonly import QueryRejected, run_sql_readonly

CORRECT_SQL = """
SELECT r.name AS region, COUNT(*) AS retrasados
FROM orders o JOIN regions r ON r.region_id = o.region_id
WHERE o.promised_at >= '2026-03-01' AND o.promised_at < '2026-04-01'
  AND (o.delivered_at > o.promised_at OR o.delivered_at IS NULL)
  AND o.status != 'cancelado'
GROUP BY r.name ORDER BY retrasados DESC, region
"""


class SqlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "demo.sqlite"
        seed_database(self.database)

    def run_sql(self, sql, **kwargs):
        return run_sql_readonly(sql, self.database, **kwargs)

    def test_query_matches_all_expected_counts(self):
        reference = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual(self.run_sql(CORRECT_SQL)["rows"], reference["por_region"])

    def test_writes_and_metadata_are_denied_without_changing_database(self):
        before = self.database.read_bytes()
        for sql in ("DELETE FROM orders", "/* comentario */ DELETE FROM orders",
                    "WITH x AS (SELECT 1) DELETE FROM orders", "SELECT * FROM demo_metadata",
                    "SELECT * FROM sqlite_master", "PRAGMA table_info(orders)",
                    "SELECT 1; SELECT 2", "SELECT load_extension('missing')"):
            with self.subTest(sql=sql), self.assertRaises(QueryRejected):
                self.run_sql(sql)
        self.assertEqual(self.database.read_bytes(), before)

    def test_cte_count_and_truncation(self):
        self.assertEqual(self.run_sql("WITH x AS (SELECT COUNT(*) AS n FROM orders) SELECT n FROM x")["rows"],
                         [{"n": 26}])
        result = self.run_sql("SELECT * FROM orders")
        self.assertEqual(len(result["rows"]), 25)
        self.assertTrue(result["truncated"])
        self.assertFalse(self.run_sql("SELECT * FROM regions")["truncated"])

    def test_query_limits(self):
        for sql in ("", "SELECT " + "1" * 4_001):
            with self.assertRaises(QueryRejected):
                self.run_sql(sql)
        for row_limit in (0, -1, 26, True):
            with self.assertRaises(QueryRejected):
                self.run_sql("SELECT 1", row_limit=row_limit)
        with self.assertRaisesRegex(QueryRejected, "SQL_TIMEOUT"):
            self.run_sql("SELECT COUNT(*) FROM orders a, orders b, orders c, orders d, orders e",
                         timeout=0.001)


if __name__ == "__main__":
    unittest.main()
