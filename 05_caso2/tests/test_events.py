from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from contracts import ControlError, digest
from events import EventLedger


class EventLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "events.sqlite"
        self.ledger = EventLedger(self.path)
        self.event = {"id": "mail-test", "sender": "personal@example.test",
                      "subject": "Solicitud", "body": "Contenido sintético"}

    def test_persistent_duplicate(self):
        self.assertTrue(self.ledger.accept(self.event))
        self.assertFalse(EventLedger(self.path).accept(self.event))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT id, hash FROM events").fetchall(),
                             [(self.event["id"], digest(self.event))])

    def test_conflict_preserves_original(self):
        self.assertTrue(self.ledger.accept(self.event))
        for field in ("sender", "subject", "body"):
            with self.subTest(field=field):
                with self.assertRaises(ControlError):
                    self.ledger.accept(dict(self.event, **{field: "changed"}))
                self.assertFalse(EventLedger(self.path).accept(self.event))
        self.assertTrue(self.ledger.accept(dict(self.event, id="another-id")))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT hash FROM events WHERE id = ?",
                                       (self.event["id"],)).fetchone(), (digest(self.event),))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)

    def test_concurrent_duplicate(self):
        ledgers = [EventLedger(self.path), EventLedger(self.path)]
        barrier = Barrier(2)

        def accept(ledger):
            barrier.wait(timeout=5)
            return ledger.accept(self.event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, ledgers))
        self.assertCountEqual(results, [True, False])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
