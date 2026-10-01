# %% [markdown]
# # Planning: un plan es una propuesta, no una autorización
#
# Objetivos: validar un plan antes de ejecutarlo y colocar la aprobación
# humana en el runtime. Prerrequisitos: SQL, JSON y el modelo configurado.
# Ejecutar: `python 01_patrones_agenticos\src\03_planning.py`.
#
# Qué quitamos: colores, replay y formatos de presentación. Conservamos
# el contrato, consultas de solo lectura, trazas y la revisión humana.
# El alcance son tres pasos; no hay replanteamiento ni envío automático.

# %%
import json

from lesson_utils import evaluate_rows, json_format, parse_json, read_prompt
from model import Llm, start
from planning_contract import PLAN_SCHEMA, needs_human, validate_plan
from sql_readonly import list_tables, safe_run, schema_text
from trace_log import Trace


# %% [markdown]
# ## 1. Pedir un plan sin conceder autoridad
#
# El formato del servidor limita la forma del JSON. El contrato local
# verifica tipos, herramientas, orden y revisión humana obligatoria.

# %%
def run(llm: Llm, trace: Trace, approve) -> dict:
    request = "Prepara un informe de los pedidos retrasados para el comité, sin compartirlo."
    system = (read_prompt("planning.txt").replace("{schema}", schema_text())
              .replace("{criterio}", read_prompt("criterio.txt")))
    response = llm.chat([{"role": "system", "content": system},
                         {"role": "user", "content": request}],
                        purpose="plan", response_format=json_format("plan", PLAN_SCHEMA))
    plan = parse_json(response.choices[0].message.content)
    errors = validate_plan(plan)
    if errors:
        raise ValueError("Plan rechazado antes de ejecutar: " + "; ".join(errors))
    trace.show("Plan validado", json.dumps(plan, ensure_ascii=False, indent=2))
    trace.emit("plan_validated", plan=plan)
    context = []
    rows_verified = False

    for step in plan["pasos"]:
        if step["ejecutor"] == "humano":
            assert rows_verified, "No hay una consulta verificada para revisar."
        if needs_human(step):
            approved = approve(step)
            trace.emit("human_decision", step=step["n"], approved=approved)
            if not approved:
                trace.show("Detenido", "La persona no aprobó. No se ejecuta este paso.")
                return {"status": "rejected", "executed_steps": len(context), "rows_verified": rows_verified}
            if step["ejecutor"] == "humano":
                trace.show("Aprobación registrada", "No se envió ningún informe ni se comprometieron recursos.")
                return {"status": "approved", "executed_steps": len(context), "rows_verified": rows_verified}
        tool = step["herramienta"]
        if tool == "run_sql_readonly":
            result = safe_run(step["sql"])
            trace.show("Resultado SQL", json.dumps(result, ensure_ascii=False, indent=2))
            trace.emit("tool_result", name=tool, result=result)
            if not result["ok"]:
                raise ValueError(result["error"])
            rows_verified, reason = evaluate_rows(result["rows"])
            trace.show("Comprobación independiente", reason)
            assert rows_verified, reason
        elif tool == "list_tables":
            result = {"ok": True, **list_tables()}
            trace.show("Esquema", json.dumps(result, ensure_ascii=False))
        else:
            assert rows_verified, "No se redacta un informe sin datos verificados."
            response = llm.chat([
                {"role": "system", "content": "Redacta en español, máximo cinco líneas. No inventes cifras."},
                {"role": "user", "content": f"Acción: {step['accion']}\nDatos: {json.dumps(context, ensure_ascii=False)}"},
            ], purpose=f"paso {step['n']}")
            text = response.choices[0].message.content
            assert isinstance(text, str) and text.strip(), "No se recibió el resumen."
            trace.show("Resumen para revisión", text)
            result = {"ok": True, "texto": text}
        context.append(result)
    raise ValueError("El plan terminó sin revisión humana.")


# %% [markdown]
# ## 2. El checkpoint pertenece a la aplicación
#
# Se revisa antes de cualquier paso de riesgo alto, aunque lo haya propuesto
# el modelo. La ausencia de una respuesta de la persona no significa permiso.

# %%
def ask_approval(trace: Trace, step: dict, auto: str | None) -> bool:
    trace.show("Revisión humana", f"Paso {step['n']}: {step['accion']}")
    if auto is not None:
        trace.show("Decisión del operador", f"Indicada por argumento: {auto}")
        return auto == "s"
    try:
        answer = input("¿Apruebas? [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        trace.show("Sin aprobación", "No se recibió una decisión. Se rechaza el paso.")
        return False
    return answer == "s"


# %% [markdown]
# ## En producción
#
# La identidad y la aprobación requieren autenticación y un registro
# persistente. `--aprobar` es una decisión explícita del operador para este
# laboratorio, no un mecanismo de autorización institucional.
# Los conteos se verifican en código; la persona debe revisar también el texto.
#
# Para recordar: JSON válido no equivale a plan permitido; un error detiene
# el flujo; aprobar aquí registra una decisión, nunca realiza un envío.

# %%
def main() -> int:
    args, backend = start("Plan acotado con revisión humana.",
                          lambda parser: parser.add_argument("--aprobar", choices=("s", "n")))
    trace = Trace("03_planning", backend.name, backend.model)
    try:
        result = run(Llm(backend, trace), trace, lambda step: ask_approval(trace, step, args.aprobar))
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    trace.end(completed=True, **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
