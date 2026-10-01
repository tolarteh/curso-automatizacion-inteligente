# %% [markdown]
# # Reflection: proponer, criticar y verificar
#
# Objetivos: identificar el ciclo de reflexión y distinguir la opinión del
# crítico de una comprobación determinista. Prerrequisitos: SQL y un modelo
# configurado en el entorno del tema. Ejecutar desde la raíz del repositorio:
# `python 01_patrones_agenticos\src\01_reflection.py`.
#
# Qué quitamos: colores de terminal, replay y el modo de borrador fijo.
# Conservamos el modelo real, dos rondas como máximo, SQL de solo lectura
# y una traza. Una crítica convincente puede seguir estando equivocada.

# %%
import json

from lesson_utils import evaluate_rows, expected, extract_sql, json_format, parse_json, read_prompt
from model import Llm, start
from sql_readonly import QueryRejected, run_sql_readonly, schema_text
from trace_log import Trace

MAX_ROUNDS = 2
CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {"cumple": {"type": "boolean"},
                   "problemas": {"type": "array", "items": {"type": "string"}}},
    "required": ["cumple", "problemas"], "additionalProperties": False,
}


# %% [markdown]
# ## 1. Datos pequeños y una referencia que el crítico no decide
#
# Los 26 pedidos incluyen cancelaciones, fechas con hora y entregas pendientes.
# Cada SQL propuesto pasa por la misma política de lectura. Sus filas son
# observables; el modelo no recibe permisos para cambiar los datos.

# %%
def execute(trace: Trace, sql: str):
    trace.show("Consulta propuesta", sql)
    try:
        rows = run_sql_readonly(sql)["rows"]
    except QueryRejected as exc:
        trace.show("Consulta rechazada", str(exc))
        return None
    trace.show("Filas obtenidas", json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


def validate_critique(critique) -> None:
    if not isinstance(critique, dict) or set(critique) != {"cumple", "problemas"}:
        raise ValueError("La crítica no cumple su contrato.")
    problems = critique["problemas"]
    if type(critique["cumple"]) is not bool or not isinstance(problems, list):
        raise ValueError("Tipos inválidos en la crítica.")
    if not all(isinstance(problem, str) for problem in problems):
        raise ValueError("Cada problema debe ser texto.")
    if critique["cumple"] and problems:
        raise ValueError("La crítica afirma que cumple, pero enumera problemas.")


# %% [markdown]
# ## 2. Construir el ciclo con un límite visible
#
# V1 es el primer SQL. V2 incorpora la crítica. No agregamos rondas indefinidas
# hasta obtener una respuesta que parezca correcta.

# %%
def run(llm: Llm, trace: Trace) -> dict:
    request = read_prompt("pedido.txt")
    instructions = read_prompt("reflection.txt")
    schema = schema_text()
    criterion = read_prompt("criterio.txt")
    trace.show("Pedido", request)
    response = llm.chat([
        {"role": "system", "content": f"{instructions}\nAplica BORRADOR.\nEsquema:\n{schema}"},
        {"role": "user", "content": request},
    ], purpose="borrador")
    sql = extract_sql(response.choices[0].message.content)
    rows = execute(trace, sql)
    first_passed = rows is not None and evaluate_rows(rows)[0]
    corrections = 0

    for round_number in range(1, MAX_ROUNDS + 1):
        response = llm.chat([
            {"role": "system", "content": f"{instructions}\nAplica CRÍTICA.\nCriterio:\n{criterion}\nEsquema:\n{schema}"},
            {"role": "user", "content": f"Pedido: {request}\nSQL: {sql}\nFilas: {json.dumps(rows, ensure_ascii=False)}"},
        ], purpose=f"crítica {round_number}", response_format=json_format("critica", CRITIQUE_SCHEMA))
        critique = parse_json(response.choices[0].message.content)
        validate_critique(critique)
        trace.show(f"Crítica {round_number}", json.dumps(critique, ensure_ascii=False))
        if critique["cumple"]:
            break
        response = llm.chat([
            {"role": "system", "content": f"{instructions}\nAplica CORRECCIÓN.\nCriterio:\n{criterion}\nEsquema:\n{schema}"},
            {"role": "user", "content": f"Pedido: {request}\nSQL anterior: {sql}\nProblemas: {critique['problemas']}"},
        ], purpose=f"corrección {round_number}")
        sql = extract_sql(response.choices[0].message.content)
        rows = execute(trace, sql)
        corrections += 1

    assert rows is not None, "La consulta final fue rechazada."
    passed, reason = evaluate_rows(rows)
    trace.show("Comprobación independiente", reason)
    assert passed, reason
    assert expected()["total_retrasados"] == 11
    return {"first_passed": first_passed, "last_passed": passed, "corrections": corrections}


# %% [markdown]
# ## 3. Comprobarlo sin pedirle al modelo que se califique
#
# El final de `run` compara los cuatro conteos con una referencia conocida,
# no solamente el total. Un crítico que acepta SQL incorrecto no logra aprobar.
#
# ## En producción
#
# Usar un conjunto de evaluación independiente, no solo estos pedidos.
# Registrar qué versión cambió y por qué; la reflexión no garantiza mejoras.
# Mantener los límites y permisos fuera del prompt.
#
# Para recordar: borrador, crítica y corrección son llamadas diferentes;
# el criterio pertenece al proceso; la verificación pertenece al código.

# %%
def main() -> int:
    _, backend = start("Reflection con SQL de solo lectura y verificación independiente.")
    trace = Trace("01_reflection", backend.name, backend.model)
    try:
        result = run(Llm(backend, trace), trace)
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    trace.end(completed=True, **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
