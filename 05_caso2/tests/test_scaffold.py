import threading
import unittest
from contracts import ControlError, ROOT, digest, read_json
from events import fetch_events, server


class ScaffoldTests(unittest.TestCase):
    def test_canonical_hash(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_synthetic_api(self):
        api = server(0)
        worker = threading.Thread(target=api.serve_forever)
        worker.start()
        try:
            events = fetch_events(f"http://127.0.0.1:{api.server_port}")
            self.assertEqual(events, read_json(ROOT / "data" / "messages.json"))
            with self.assertRaises(ControlError):
                fetch_events(f"http://127.0.0.1:{api.server_port}", max_pages=1)
            with self.assertRaises(ControlError):
                fetch_events("https://example.test")
        finally:
            api.shutdown()
            worker.join()
            api.server_close()
