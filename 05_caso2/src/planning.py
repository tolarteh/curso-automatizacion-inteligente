"""Plan concreto: no confundir ausencia con inventario incompleto."""
from datetime import date
from contracts import ControlError, FIELDS, ROLES, Status, digest


def validate_request(request, personnel, today):
    try:
        effective = date.fromisoformat(request["effective_date"])
        clock = date.fromisoformat(today)
    except (ValueError, KeyError) as exc:
        raise ControlError("Fecha inválida; usar reloj ISO explícito.") from exc
    record = personnel.get(request.get("request_id"))
    if not record or any(request.get(key) != record[key] for key in FIELDS if key != "request_id"):
        raise ControlError("Identidad o fecha contradictoria con registro de personal.")
    if effective > clock:
        raise ControlError("Fecha futura: no ejecutar anticipadamente.")


def build_plan(request, inventory, version=1):
    if not inventory.get("complete"):
        raise ControlError("Visibilidad desconocida: no se puede afirmar ausencia.")
    username = request["username"]
    user = inventory["users"].get(username)
    if user is None:
        raise ControlError("Usuario no encontrado.")
    actions = [{"kind": "block", "target": username}]
    for field in ("tokens", "teams", "repos"):
        for target in sorted(user[field]):
            actions.append({"kind": field, "target": target})
    plan = {"request": request, "version": version, "inventory_hash": digest(inventory),
            "inventory": inventory, "actions": actions, "warnings": [
                f"Transferencia de propietario pendiente: {repo}" for repo in user["sole_owner"]]}
    for action in actions:
        action["id"] = digest({"request_id": request["request_id"], "user": username, **action})
    plan["hash"] = plan_hash(plan)
    return plan


def plan_hash(plan):
    # TODO P1: hash canónico del plan completo excluyendo solo su propio hash.
    raise NotImplementedError("TODO P1: ligar autorización al contenido")


def approve(case, actor, role, decision, plan_hash_value, version):
    if case["status"] != Status.PENDING:
        raise ControlError("El caso no está pendiente de aprobación.")
    plan = case["plan"]
    if plan["hash"] != plan_hash(plan):
        raise ControlError("Plan alterado.")
    if not actor.strip() or role not in ROLES or decision not in {"approve", "reject"}:
        raise ControlError("Actor, rol o decisión inválidos.")
    if plan_hash_value != plan["hash"] or version != plan["version"]:
        raise ControlError("Aprobación de versión vieja.")
    # TODO P2: bloquear duplicación de rol o actor, registrar hash, versión
    # y evidencia; rechazo cambia status a RECHAZADO. Identidad declarada.
    raise NotImplementedError("TODO P2: exigir dos roles distintos")


def ensure_authorized(case):
    # TODO P3: comprobar ambos roles, distintos actores, decisión approve,
    # hash y versión actuales. Nunca aceptar solo len(approvals) == 2.
    raise NotImplementedError("TODO P3: verificar autorización completa")
