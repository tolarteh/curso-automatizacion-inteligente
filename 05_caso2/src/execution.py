"""Cambios exclusivamente sobre JSON sintético, con reconciliación."""
import copy
from contracts import ControlError, Status, digest, read_json, write_json
from planning import ensure_authorized, plan_hash


def apply_action(inventory, username, action):
    result = copy.deepcopy(inventory)
    user = result["users"][username]
    if action["kind"] == "block":
        user["blocked"] = True
    elif action["kind"] in {"tokens", "teams", "repos"}:
        values = user[action["kind"]]
        if action["target"] in values:
            values.remove(action["target"])
    else:
        raise ControlError("Operación no permitida.")
    if result != inventory:
        result["revision"] += 1
    return result


def expected_state(case, count):
    result = copy.deepcopy(case["plan"]["inventory"])
    for action in case["plan"]["actions"][:count]:
        result = apply_action(result, case["plan"]["request"]["username"], action)
    return result


def execute(case, inventory_path, persist, fail_after=None, crash_after_change=None):
    ensure_authorized(case)
    if case["plan"]["hash"] != plan_hash(case["plan"]):
        raise ControlError("Plan alterado.")
    completed = len(case["journal"])
    actual = read_json(inventory_path)
    before = expected_state(case, completed)
    actions = case["plan"]["actions"]
    if actual != before:
        next_action = actions[completed] if completed < len(actions) else None
        if (next_action and case.get("pending_action") == next_action["id"]
                and actual == expected_state(case, completed + 1)):
            case["journal"].append({"id": next_action["id"], "before": digest(before),
                                    "after": digest(actual), "reconciled": True})
            case["pending_action"] = None
            persist(case)
        else:
            case["status"] = Status.STALE
            case["approvals"] = []
            persist(case)
            raise ControlError("Inventario cambió: plan y aprobaciones invalidados.")
    for index in range(len(case["journal"]), len(actions)):
        action = actions[index]
        before = read_json(inventory_path)
        if before != expected_state(case, index):
            case["status"] = Status.STALE
            case["approvals"] = []
            persist(case)
            raise ControlError("Inventario cambió durante la ejecución.")
        after = apply_action(before, case["plan"]["request"]["username"], action)
        case["pending_action"] = action["id"]
        case["status"] = Status.PARTIAL
        persist(case)
        write_json(inventory_path, after)
        if crash_after_change == index + 1:
            raise ControlError("Corte inyectado entre cambio y registro.")
        verified = read_json(inventory_path)
        if verified != after:
            raise ControlError("Verificación posterior falló.")
        case["journal"].append({"id": action["id"], "before": digest(before),
                                "after": digest(verified), "reconciled": False})
        case["pending_action"] = None
        persist(case)
        if fail_after == index + 1:
            raise ControlError("Fallo parcial inyectado; reanudar explícitamente.")
    case["status"] = Status.DONE
    persist(case)
    return case


def close_report(case, output):
    plan = case["plan"]
    done_ids = {entry["id"] for entry in case["journal"]}
    report = {"case_id": case["case_id"], "plan_hash": plan["hash"], "version": plan["version"],
              "status": case["status"], "verified": case["journal"],
              "pending": [action for action in plan["actions"] if action["id"] not in done_ids],
              "manual_pending": plan["warnings"], "errors": case.get("errors", [])}
    if report["status"] == Status.DONE and report["manual_pending"]:
        report["status"] = "CAMBIOS_COMPROBADOS_CON_PENDIENTES_MANUALES"
    write_json(output / "report.json", report)
    lines = [f"# Cierre {case['case_id']}", "", f"Estado: {report['status']}",
             f"Plan: {plan['hash']} (versión {plan['version']})", "",
             f"Acciones comprobadas: {len(done_ids)}", f"Acciones pendientes: {len(report['pending'])}"]
    for entry in report["verified"]:
        lines.append(f"- {entry['id']}: {entry['before']} -> {entry['after']}")
    for item in report["manual_pending"]:
        lines.append(f"- Pendiente manual: {item}")
    for error in report["errors"]:
        lines.append(f"- Fallo registrado: {error}")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "notification.txt").write_text(
        f"BORRADOR LOCAL, NO ENVIADO\nCaso {case['case_id']}: {report['status']}.\n"
        f"Comprobadas {len(done_ids)}, pendientes {len(report['pending'])}.\n", encoding="utf-8")
    return report
