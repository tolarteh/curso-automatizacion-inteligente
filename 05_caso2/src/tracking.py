"""Run por segmento: FINISHED técnico no significa baja terminada."""
from contextlib import contextmanager
import os
import time
from urllib.parse import urlparse

from contracts import ControlError, ROOT, digest


class Tracker:
    def __init__(self, case_id, segment, level="metrics", test_uri=None):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        if level not in {"metrics", "traces"}:
            raise ControlError("Nivel MLflow inválido.")
        if level == "traces" and os.getenv("SYNTHETIC_TRACES") != "1":
            raise ControlError("Traces solo con datos sintéticos y selección explícita.")
        import mlflow
        import mlflow.langchain
        uri = test_uri or os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5005")
        if not test_uri:
            parsed = urlparse(uri)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
                raise ControlError("MLflow debe ser local.")
            if not all(os.getenv(key) for key in ("MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD")):
                raise ControlError("MLflow exige usuario y contraseña del servidor local.")
        self.mlflow, self.level = mlflow, level
        mlflow.set_tracking_uri(uri)
        if test_uri:
            client = mlflow.tracking.MlflowClient()
            if not client.get_experiment_by_name("synthetic-offboarding"):
                location = ROOT / "outputs" / "tests" / "mlflow-artifacts"
                client.create_experiment("synthetic-offboarding", artifact_location=location.as_uri())
        mlflow.set_experiment("synthetic-offboarding")
        self.case_id, self.segment = case_id, segment
        self.start = time.perf_counter()

    def __enter__(self):
        self.mlflow.start_run(run_name=self.segment)
        self.mlflow.set_tags({"case_id": self.case_id, "thread_id": self.case_id,
                             "segment": self.segment, "identity_assurance": "self-declared",
                             "mlflow_writer": os.getenv("MLFLOW_TRACKING_USERNAME", "local-cpu")})
        self.mlflow.log_params({"observability": self.level, "max_model_calls": 1,
                               "prompt_hash": digest((ROOT / "prompts" / "extract.txt").read_text(encoding="utf-8"))})
        if self.level == "traces":
            self._install_lifecycle_callbacks()
            self.mlflow.langchain.autolog(log_traces=True, silent=False)
        return self

    def _install_lifecycle_callbacks(self):
        from mlflow.langchain.langchain_tracer import MlflowLangchainTracer
        self.callback_class = MlflowLangchainTracer
        self.added_callbacks = []
        # MLflow 3.16.1 aún no implementa los callbacks de pausa de LangGraph
        # 1.2.12. El puente se limita al segmento, no modifica la instalación.
        def lifecycle_callback(tracer, event):
            span = self.mlflow.get_current_active_span()
            if span:
                span.set_attribute("langgraph.lifecycle", type(event).__name__)
                span.set_attribute("checkpoint_id", event.checkpoint_id)
        for name in ("on_interrupt", "on_resume"):
            if not hasattr(MlflowLangchainTracer, name):
                setattr(MlflowLangchainTracer, name, lifecycle_callback)
                self.added_callbacks.append(name)

    @contextmanager
    def span(self, name, case=None):
        # Nunca pasar el estado completo a spans de nivel metrics.
        with self.mlflow.start_span(name=name, span_type="CHAIN") as span:
            span.set_attributes({"case_id": self.case_id, "thread_id": self.case_id})
            if case and case.get("plan"):
                span.set_attribute("plan_hash", case["plan"]["hash"])
            try:
                yield span
            except Exception as exc:
                span.set_attribute("error_type", type(exc).__name__)
                raise

    def record(self, case, stats=None):
        self.mlflow.set_tag("business_status", str(case["status"]))
        if case.get("plan"):
            self.mlflow.set_tags({"plan_hash": case["plan"]["hash"], "plan_version": case["plan"]["version"]})
            self.mlflow.log_metric("actions_proposed", len(case["plan"]["actions"]))
        self.mlflow.log_metrics({"actions_verified": len(case.get("journal", [])),
                                "approvals": len(case.get("approvals", []))})
        if stats:
            self.mlflow.log_metrics({key: stats[key] for key in ("calls", "tokens", "latency_ms")})
            self.mlflow.log_params({key: stats[key] for key in ("route", "provider", "model") if key in stats})

    def __exit__(self, kind, error, traceback):
        try:
            self.mlflow.log_metric("duration_ms", (time.perf_counter() - self.start) * 1000)
            if error:
                self.mlflow.set_tag("error_type", kind.__name__)
            self.mlflow.end_run(status="FAILED" if error else "FINISHED")
            self.mlflow.flush_trace_async_logging()
        finally:
            if self.level == "traces":
                self.mlflow.langchain.autolog(disable=True)
                for name in self.added_callbacks:
                    delattr(self.callback_class, name)
        return False
