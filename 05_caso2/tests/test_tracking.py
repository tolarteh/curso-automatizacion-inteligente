import unittest
from unittest.mock import patch
from contracts import ROOT, Status
from tracking import Tracker


class TrackingTests(unittest.TestCase):
    def test_local_metrics_and_span(self):
        from mlflow.tracking import MlflowClient
        path = ROOT / "outputs" / "tests" / "mlflow.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        uri = f"sqlite:///{path.as_posix()}"
        with Tracker("synthetic-test", "approval", test_uri=uri) as tracker:
            run_id = tracker.mlflow.active_run().info.run_id
            with tracker.span("authorization"):
                tracker.record({"status": Status.PENDING, "approvals": []})
        run = MlflowClient(tracking_uri=uri).get_run(run_id)
        self.assertEqual(run.info.status, "FINISHED")
        self.assertEqual(run.data.tags["business_status"], Status.PENDING)
        self.assertEqual(run.data.tags["case_id"], "synthetic-test")
        traces = tracker.mlflow.search_traces(experiment_ids=[run.info.experiment_id], return_type="list")
        self.assertTrue(traces)

    def test_opt_in_graph_autolog(self):
        import sqlite3
        from approval_graph import build_graph
        from extraction import structured
        from planning import build_plan
        from contracts import read_json
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = ROOT / "outputs" / "tests"
        uri = f"sqlite:///{(path / 'mlflow-traces.db').as_posix()}"
        request = structured(read_json(ROOT / "data" / "messages.json")[0]["body"])
        plan = build_plan(request, read_json(ROOT / "data" / "inventory.json"))
        case = {"case_id": "trace-test", "status": Status.PENDING, "plan": plan, "approvals": []}
        with patch.dict("os.environ", {"SYNTHETIC_TRACES": "1"}):
            with Tracker("trace-test", "pause", level="traces", test_uri=uri) as tracker:
                with sqlite3.connect(":memory:", check_same_thread=False) as db:
                    graph = build_graph(SqliteSaver(db))
                    paused = graph.invoke({"case": case}, {"configurable": {"thread_id": "trace-test"}})
                    self.assertIn("__interrupt__", paused)
                tracker.record(case)
                experiment = tracker.mlflow.active_run().info.experiment_id
        traces = tracker.mlflow.search_traces(experiment_ids=[experiment], return_type="list")
        self.assertTrue(any(any(span.name == "LangGraph" for span in trace.data.spans) for trace in traces))
