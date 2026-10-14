import unittest
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
