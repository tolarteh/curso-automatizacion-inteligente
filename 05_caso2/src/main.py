"""Demo por correo: política, aprobación y cambios en Git sintético."""
import json
import os

from contracts import ControlError, ROOT, Status, digest

SCENARIOS = {
    "mail-001": "Formulario: cero inferencia y propietario pendiente",
    "mail-002": "Prosa libre: extracción real con evidencia",
    "mail-003": "Remitente ajeno: debe bloquearse antes del plan",
    "mail-004": "Mensaje irrelevante: no debe producir una baja",
    "mail-005": "Prompt injection: el correo no autoriza acciones",
    "mail-006": "Corrección: fecha contradictoria con registro de personal",
}


def select(items, prompt):
    for index, (_, label) in enumerate(items, 1):
        print(f"{index}. {label}")
    print("0. Volver / salir")
    choice = input(prompt).strip()
    if choice == "0":
        return None
    if not choice.isdigit() or not 1 <= int(choice) <= len(items):
        raise ControlError("Opción inválida.")
    return items[int(choice) - 1][0]


def show_case(case):
    print(f"\nEstado: {case['status']} | Caso: {case['case_id']}")
    plan = case.get("plan")
    if plan:
        print(f"Hash: {plan['hash']} | Versión: {plan['version']}")
        print("Solicitud:", json.dumps(plan["request"], ensure_ascii=False))
        for action in plan["actions"]:
            print(f"  {action['kind']}: {action['target']}")
        for warning in plan["warnings"]:
            print("Pendiente manual:", warning)
    for approval in case["approvals"]:
        print(f"  {approval['role']}: {approval['actor']} ({approval['decision']})")
    print(f"Acciones comprobadas: {len(case['journal'])} | Pending: {case['pending_action']}")
    if case.get("errors"):
        print("Errores históricos (no incluyen el mensaje original):", case["errors"])
    print("MLflow: http://127.0.0.1:5005, synthetic-offboarding; filtrar por case_id.")


def demonstrate(event, today, level):
    import service
    from openai import APIError

    print(f"\n{event['id']}: {SCENARIOS.get(event['id'], event['subject'])}")
    print(f"Remitente: {event['sender']}\n{event['body']}")
    path = service.case_path(digest(event["id"]))
    if not path.exists():
        print("La prosa libre requiere inferencia autorizada; el formulario no usa modelo.")
        if input("Procesar este correo [si/no]: ").strip() != "si":
            return
        try:
            service.ingest(event, today, level)
        except (ValueError, OSError, ImportError, APIError) as exc:
            print(f"CONTROL / FALLO REAL ({type(exc).__name__}): {exc}")
            print("No se declara éxito ni se cambia de proveedor.")
    else:
        print("Caso ya guardado: no se repite extracción ni se generan nuevas trazas de ingesta.")
    if not path.exists():
        return
    while True:
        case = service.load(digest(event["id"]))
        show_case(case)
        if "plan" not in case:
            print("Sin plan: no hay acciones autorizables. No se reintenta ni borra este caso.")
            input("Enter para volver a los correos.")
            return
        try:
            action = select([
                ("manager", "Aprobar como manager"),
                ("security", "Aprobar como security"),
                ("reject", "Rechazar el plan"),
                ("same_actor", "Demostrar rechazo: mismo actor en el otro rol"),
                ("old_hash", "Demostrar rechazo: hash viejo"),
                ("execute", "Ejecutar / reanudar y mostrar cierre"),
                ("partial", "Demostrar fallo parcial tras dos acciones"),
                ("crash", "Demostrar corte entre cambio y registro"),
                ("replan", "Replanificar inventario invalidado"),
            ], "Demo sobre este correo: ")
            if action is None:
                return
            plan = case["plan"]
            if action in {"manager", "security", "reject", "same_actor", "old_hash"}:
                if action in {"same_actor", "old_hash"}:
                    if len(case["approvals"]) != 1:
                        raise ControlError("Esta demo requiere exactamente una aprobación previa.")
                    first = case["approvals"][0]
                    role = "security" if first["role"] == "manager" else "manager"
                    actor = first["actor"] if action == "same_actor" else input("Otro actor: ").strip()
                else:
                    role = action if action != "reject" else select(
                        [("manager", "manager"), ("security", "security")], "Rol que rechaza: ")
                    if role is None:
                        continue
                    actor = input(f"Actor {role} (identidad declarada): ").strip()
                service.decide(case["case_id"], actor, role,
                               "reject" if action == "reject" else "approve",
                               "hash-viejo" if action == "old_hash" else plan["hash"],
                               plan["version"], level)
                print("Decisión registrada; aprobar no ejecuta Git.")
            elif action == "replan":
                if input("Crear nueva versión y borrar aprobaciones [si/no]: ").strip() == "si":
                    service.replan(case["case_id"], today, level)
            else:
                if action != "execute" and (case["journal"] or case["pending_action"]
                                            or case["status"] == Status.DONE):
                    raise ControlError("Inyectar fallos requiere un caso aprobado sin ejecución previa.")
                if input("Cambiar Git sintético con esta demo [si/no]: ").strip() != "si":
                    continue
                service.run_execution(case["case_id"], today,
                                      fail_after=2 if action == "partial" else None,
                                      crash_after_change=1 if action == "crash" else None, level=level)
        except (ValueError, OSError, ImportError, APIError) as exc:
            print(f"CONTROL / FALLO REAL ({type(exc).__name__}): {exc}")
            print("No se declara éxito. El estado y diario permiten diagnosticar o reanudar.")
        report = path.with_name("report.md")
        if report.exists():
            print(report.read_text(encoding="utf-8"))


def main():
    from dotenv import load_dotenv
    from events import fetch_events
    from openai import APIError

    load_dotenv(ROOT / ".env", override=False)
    today = "2026-10-14"
    level = "traces" if os.getenv("SYNTHETIC_TRACES") == "1" else "metrics"
    print("Demo de correos y Git sintéticos. Identidades declaradas, no autenticadas.")
    print(f"Fecha: {today} | Observabilidad: {level} | Proveedor: {os.getenv('MODEL_PROVIDER', 'groq')}")
    print("API de correo y MLflow deben estar arrancados. No se habilita inferencia automáticamente.")
    while True:
        try:
            events = fetch_events()
            event = select([(event, f"{event['id']}: {SCENARIOS.get(event['id'], event['subject'])}")
                            for event in events], "Correo para demostrar: ")
            if event is None:
                return
            demonstrate(event, today, level)
        except (ValueError, OSError, ImportError, APIError) as exc:
            print(f"ERROR ({type(exc).__name__}): {exc}")
            if input("Enter para reintentar, 0 para salir: ").strip() == "0":
                return


if __name__ == "__main__":
    main()
