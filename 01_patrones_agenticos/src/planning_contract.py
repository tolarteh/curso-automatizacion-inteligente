"""Contrato del plan y política de revisión humana para el informe."""
EXECUTORS = ("software", "llm", "humano")
TOOLS = ("list_tables", "run_sql_readonly", "ninguna")
STEP_FIELDS = {"n", "accion", "ejecutor", "herramienta", "sql", "riesgo"}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "objetivo": {"type": "string"},
        "pasos": {
            "type": "array", "minItems": 3, "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"}, "accion": {"type": "string"},
                    "ejecutor": {"type": "string", "enum": list(EXECUTORS)},
                    "herramienta": {"type": "string", "enum": list(TOOLS)},
                    "sql": {"type": "string"},
                    "riesgo": {"type": "string", "enum": ["bajo", "alto"]},
                },
                "required": sorted(STEP_FIELDS), "additionalProperties": False,
            },
        },
    },
    "required": ["objetivo", "pasos"], "additionalProperties": False,
}


def needs_human(step: dict) -> bool:
    return step["ejecutor"] == "humano" or step["riesgo"] == "alto"


def validate_plan(plan) -> list[str]:
    if not isinstance(plan, dict) or set(plan) != {"objetivo", "pasos"}:
        return ["Se necesita un objeto con objetivo y pasos, sin campos adicionales."]
    if not isinstance(plan["objetivo"], str) or not plan["objetivo"].strip():
        return ["El objetivo debe ser texto no vacío."]
    steps = plan["pasos"]
    if not isinstance(steps, list) or len(steps) != 3:
        return ["Se necesitan exactamente tres pasos."]
    errors = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or set(step) != STEP_FIELDS:
            errors.append(f"Paso {index}: campos faltantes o adicionales.")
            continue
        if type(step["n"]) is not int or step["n"] != index:
            errors.append(f"Paso {index}: numeración incorrecta.")
        if not isinstance(step["accion"], str) or not step["accion"].strip():
            errors.append(f"Paso {index}: acción vacía.")
        if step["ejecutor"] not in EXECUTORS or step["herramienta"] not in TOOLS:
            errors.append(f"Paso {index}: ejecutor o herramienta fuera de la lista permitida.")
        if step["riesgo"] not in ("bajo", "alto") or not isinstance(step["sql"], str):
            errors.append(f"Paso {index}: riesgo o SQL inválido.")
            continue
        if step["herramienta"] == "run_sql_readonly":
            if not step["sql"].strip() or step["ejecutor"] != "software":
                errors.append(f"Paso {index}: SQL requiere texto y ejecutor software.")
        elif step["sql"]:
            errors.append(f"Paso {index}: SQL sin herramienta SQL.")
        if step["ejecutor"] == "software" and step["herramienta"] == "ninguna":
            errors.append(f"Paso {index}: el software necesita una herramienta determinista.")
        if step["ejecutor"] in ("llm", "humano") and step["herramienta"] != "ninguna":
            errors.append(f"Paso {index}: este ejecutor no invoca herramientas.")
        if step["ejecutor"] == "humano" and index != 3:
            errors.append(f"Paso {index}: la revisión humana es terminal en este proceso.")
    last = steps[-1]
    if not isinstance(last, dict) or last.get("ejecutor") != "humano" or last.get("riesgo") != "alto":
        errors.append("El último paso debe exigir revisión humana de riesgo alto.")
    return errors
