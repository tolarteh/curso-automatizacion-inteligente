"""Orquestación de CLI, persistencia y observabilidad fuera de los ejercicios."""
from contextlib import contextmanager
import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from approval_graph import build_graph
from contracts import ControlError, ROOT, Status, digest, read_json, write_json
from events import EventLedger
from execution import close_report, execute
from extraction import extract, validate_evidence
from planning import build_plan, validate_request
from tracking import Tracker

OUTPUT = ROOT / "outputs"


@contextmanager
def exclusive():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "writer.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ControlError("Otro escritor o corte previo: revisar writer.lock manualmente.") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink()


def case_path(case_id):
    if len(case_id) != 64 or any(char not in "0123456789abcdef" for char in case_id):
        raise ControlError("case_id debe ser un hash SHA-256.")
    return OUTPUT / "cases" / case_id / "case.json"


def save(case):
    write_json(case_path(case["case_id"]), case)


def load(case_id):
    return read_json(case_path(case_id))


def initialize_inventory():
    path = OUTPUT / "git.json"
    if not path.exists():
        write_json(path, read_json(ROOT / "data" / "inventory.json"))
    return path


def audit(case, event, details=None):
    path = case_path(case["case_id"]).parent / "audit.jsonl"
    import json
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": event, "case_id": case["case_id"],
                                 "plan_hash": case.get("plan", {}).get("hash"),
                                 "details": details or {}}, ensure_ascii=False) + "\n")


def approval_segment(case, decision=None):
    with sqlite3.connect(OUTPUT / "checkpoints.sqlite", check_same_thread=False) as db:
        graph = build_graph(SqliteSaver(db))
        config = {"configurable": {"thread_id": f"{case['case_id']}:{case['plan']['version']}"}}
        if decision is None:
            result = graph.invoke({"case": case}, config)
        else:
            snapshot = graph.get_state(config)
            if not snapshot.next:
                raise ControlError("No hay checkpoint pendiente; no aprobar por fuera del grafo.")
            if snapshot.values["case"]["plan"]["hash"] != case["plan"]["hash"]:
                raise ControlError("Checkpoint de otro plan.")
            result = graph.invoke(Command(resume=decision), config)
        save(result["case"])
        return result["case"]


def ingest(event, today, level="metrics", provider=None):
    case_id = digest(event["id"])
    with exclusive():
        accepted = EventLedger(OUTPUT / "events.sqlite").accept(event)
        if not accepted and case_path(case_id).exists():
            return load(case_id)
        case = {"case_id": case_id, "event_hash": digest(event), "status": "RECIBIDO",
                "approvals": [], "journal": [], "pending_action": None, "errors": []}
        save(case)
        try:
            with Tracker(case_id, "ingestion", level) as tracker:
                with tracker.span("extraction"):
                    extracted, stats = extract(event, provider)
                with tracker.span("policy"):
                    request = validate_evidence(event, extracted)
                    validate_request(request, read_json(ROOT / "data" / "personnel.json"), today)
                version = 1
                for path in (OUTPUT / "cases").glob("*/case.json"):
                    previous = read_json(path)
                    old_request = previous.get("plan", {}).get("request")
                    if previous["case_id"] == case_id or not old_request:
                        continue
                    if old_request["request_id"] == request["request_id"]:
                        if old_request == request and previous["status"] != Status.STALE:
                            case.update(status="SOLICITUD_DUPLICADA", duplicate_of=previous["case_id"])
                            save(case)
                            tracker.record(case, stats)
                            return case
                        version = max(version, previous["plan"]["version"] + 1)
                        previous.update(status=Status.STALE, approvals=[])
                        save(previous)
                        audit(previous, "superseded", {"new_case_id": case_id})
                with tracker.span("planning"):
                    case["plan"] = build_plan(request, read_json(initialize_inventory()), version)
                    case["status"] = Status.PENDING
                    case = approval_segment(case)
                audit(case, "plan_prepared")
                tracker.record(case, stats)
        except Exception as exc:
            case["status"] = Status.REJECTED
            case["errors"].append(type(exc).__name__)
            save(case)
            audit(case, "ingestion_failed", {"error_type": type(exc).__name__})
            raise
        return case


def decide(case_id, actor, role, decision, hash_value, version, level="metrics"):
    with exclusive():
        case = load(case_id)
        if case["status"] != Status.PENDING:
            raise ControlError("Caso no pendiente.")
        if digest(read_json(initialize_inventory())) != case["plan"]["inventory_hash"]:
            case.update(status=Status.STALE, approvals=[])
            save(case)
            audit(case, "inventory_changed")
            raise ControlError("Inventario cambió; volver a planificar.")
        with Tracker(case_id, "approval", level) as tracker:
            with tracker.span("human_approval", case):
                case = approval_segment(case, {"actor": actor, "role": role, "decision": decision,
                                               "hash": hash_value, "version": version})
            audit(case, "approval", {"actor": actor, "role": role, "decision": decision})
            tracker.record(case)
        return case


def run_execution(case_id, today, fail_after=None, crash_after_change=None, level="metrics"):
    with exclusive():
        case = load(case_id)
        validate_request(case["plan"]["request"], read_json(ROOT / "data" / "personnel.json"), today)
        with Tracker(case_id, "execution", level) as tracker:
            try:
                with tracker.span("execute_and_verify", case):
                    execute(case, initialize_inventory(), save, fail_after, crash_after_change)
            except Exception as exc:
                case["errors"].append(type(exc).__name__)
                save(case)
                audit(case, "execution_failed", {"error_type": type(exc).__name__})
                close_report(case, case_path(case_id).parent)
                tracker.record(case)
                raise
            close_report(case, case_path(case_id).parent)
            audit(case, "execution_verified")
            tracker.record(case)
        return case


def replan(case_id, today, level="metrics"):
    with exclusive():
        case = load(case_id)
        if case["status"] != Status.STALE:
            raise ControlError("Solo replanificar un plan invalidado.")
        request = case["plan"]["request"]
        validate_request(request, read_json(ROOT / "data" / "personnel.json"), today)
        with Tracker(case_id, "replan", level) as tracker:
            case.setdefault("history", []).append({"plan": case["plan"], "journal": case["journal"]})
            case.update(plan=build_plan(request, read_json(initialize_inventory()), case["plan"]["version"] + 1),
                        status=Status.PENDING, approvals=[], journal=[], pending_action=None)
            save(case)
            case = approval_segment(case)
            audit(case, "replanned")
            tracker.record(case)
        return case
