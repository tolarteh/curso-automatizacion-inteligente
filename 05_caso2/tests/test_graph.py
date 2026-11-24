import sqlite3
import unittest
from contracts import ControlError, ROOT, Status, read_json
from approval_graph import build_graph
from extraction import structured
from planning import build_plan
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command


class GraphTests(unittest.TestCase):
    def test_restart_and_two_pauses(self):
        path = ROOT / "outputs" / "tests" / "graph.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        plan = build_plan(structured(read_json(ROOT / "data" / "messages.json")[0]["body"]),
                          read_json(ROOT / "data" / "inventory.json"))
        case = {"case_id": "graph-test", "status": Status.PENDING, "approvals": [], "plan": plan}
        config = {"configurable": {"thread_id": "graph-test"}}
        with sqlite3.connect(path, check_same_thread=False) as db:
            graph = build_graph(SqliteSaver(db))
            paused = graph.invoke({"case": case}, config)
            self.assertIn("__interrupt__", paused)
        with sqlite3.connect(path, check_same_thread=False) as db:
            graph = build_graph(SqliteSaver(db))
            decision = {"actor": "one", "role": "manager", "decision": "approve",
                        "hash": plan["hash"], "version": 1}
            paused = graph.invoke(Command(resume=decision), config)
            self.assertIn("__interrupt__", paused)
            self.assertEqual(len(paused["case"]["approvals"]), 1)
        with sqlite3.connect(path, check_same_thread=False) as db:
            graph = build_graph(SqliteSaver(db))
            decision.update(actor="two", role="security")
            completed = graph.invoke(Command(resume=decision), config)
            self.assertNotIn("__interrupt__", completed)
            self.assertEqual(len(completed["case"]["approvals"]), 2)
