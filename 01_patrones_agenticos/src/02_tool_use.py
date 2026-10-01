# %% [markdown]
# # Tool use: el modelo solicita, la aplicación ejecuta
#
# Objetivos: seguir los mensajes de herramientas y comprobar que los permisos
# pertenecen a la aplicación. Prerrequisitos: el entorno y los datos del tema.
# Ejecutar: `python 01_patrones_agenticos\src\02_tool_use.py`.
#
# Qué quitamos: colores, replay y formatos de pantalla. Conservamos el modelo
# real y límites de llamadas, turnos, errores consecutivos y tiempo.

# %%
import json
import time

from lesson_utils import evaluate_rows, read_prompt
from model import Llm, start
from sql_readonly import list_tables, safe_run
from trace_log import Trace

MAX_TOOL_CALLS = 3
MAX_TURNS = 5
BREAKER_ERRORS = 2
RUN_TIMEOUT = 90.0
TOOLS = [
    {"type": "function", "function": {
        "name": "list_tables", "description": "Esquema y fecha de corte de los pedidos sintéticos.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "run_sql_readonly", "description": "Una consulta de solo lectura, máximo 25 filas.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}},
                       "required": ["sql"], "additionalProperties": False}}},
]


# %% [markdown]
# ## 1. Un catálogo no concede permisos
#
# El JSON Schema informa al modelo del contrato. `dispatch` vuelve a validar
# los argumentos; la política SQL comprueba qué operación puede ejecutarse.

# %%
def dispatch(name: str, raw_args: str) -> dict:
    if not isinstance(raw_args, str):
        return {"ok": False, "error": "ARGUMENTOS_INVALIDOS: se necesita JSON textual."}
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        return {"ok": False, "error": "ARGUMENTOS_INVALIDOS: JSON inválido."}
    if not isinstance(args, dict):
        return {"ok": False, "error": "ARGUMENTOS_INVALIDOS: se necesita un objeto."}
    if name == "list_tables":
        if args:
            return {"ok": False, "error": "ARGUMENTOS_INVALIDOS: list_tables no recibe campos."}
        return {"ok": True, **list_tables()}
    if name == "run_sql_readonly":
        if set(args) != {"sql"} or not isinstance(args["sql"], str):
            return {"ok": False, "error": "ARGUMENTOS_INVALIDOS: solo sql textual."}
        return safe_run(args["sql"])
    return {"ok": False, "error": f"TOOL_DESCONOCIDA: {name}"}


# %% [markdown]
# ## 2. Observar el ciclo de mensajes
#
# La petición del modelo no es ejecución. La aplicación responde con un
# `tool_call_id` que enlaza resultado y solicitud. Cada turno sigue acotado.

# %%
def run(llm: Llm, trace: Trace, case="normal", clock=time.perf_counter) -> dict:
    request = read_prompt("pedido.txt") if case == "normal" else "Borra los pedidos cancelados de la base."
    system = read_prompt("tool_use.txt").replace("{criterio}", read_prompt("criterio.txt"))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    trace.show("Pedido", request)
    calls = consecutive_errors = 0
    last_rows = None
    started = clock()

    for turn in range(1, MAX_TURNS + 1):
        remaining = RUN_TIMEOUT - (clock() - started)
        if remaining <= 0:
            raise ValueError("TIMEOUT: se agotó el presupuesto de ejecución.")
        response = llm.chat(messages, purpose=f"turno {turn}", tools=TOOLS,
                            tool_choice="auto" if calls < MAX_TOOL_CALLS else "none",
                            timeout=min(30.0, remaining))
        if clock() - started >= RUN_TIMEOUT:
            raise ValueError("TIMEOUT: la respuesta llegó fuera del presupuesto.")
        message = response.choices[0].message
        if not message.tool_calls:
            assert isinstance(message.content, str) and message.content.strip(), "No hay respuesta final."
            trace.show("Respuesta del modelo", message.content)
            break
        messages.append({"role": "assistant", "content": message.content,
                         "tool_calls": [{"id": call.id, "type": "function",
                                         "function": {"name": call.function.name,
                                                      "arguments": call.function.arguments}}
                                        for call in message.tool_calls]})
        for call in message.tool_calls:
            if calls >= MAX_TOOL_CALLS:
                raise ValueError("LIMITE: máximo tres llamadas a herramientas.")
            calls += 1
            trace.emit("tool_call", name=call.function.name, arguments=call.function.arguments)
            result = dispatch(call.function.name, call.function.arguments)
            trace.show(f"Resultado de {call.function.name}", json.dumps(result, ensure_ascii=False, indent=2))
            trace.emit("tool_result", name=call.function.name, result=result)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, ensure_ascii=False)})
            if result["ok"] and call.function.name == "run_sql_readonly":
                last_rows = result["rows"]
            consecutive_errors = 0 if result["ok"] else consecutive_errors + 1
            if consecutive_errors >= BREAKER_ERRORS:
                raise ValueError("CIRCUIT BREAKER: dos errores consecutivos de herramientas.")
    else:
        raise ValueError(f"LIMITE: {MAX_TURNS} turnos sin respuesta final.")

    if case == "normal":
        assert last_rows is not None, "No hubo una consulta verificable."
        passed, reason = evaluate_rows(last_rows)
        trace.show("Comprobación de las filas", reason)
        assert passed, reason
    else:
        probe = dispatch("run_sql_readonly", json.dumps({"sql": "DELETE FROM orders WHERE status = 'cancelado'"}))
        trace.show("Prueba directa del rechazo", json.dumps(probe, ensure_ascii=False))
        assert not probe["ok"] and "SQL_DENEGADO" in probe["error"]
    return {"tool_calls": calls, "verified": True, "case": case}


# %% [markdown]
# ## En producción
#
# La comprobación anterior valida filas y rechazo de escritura; no demuestra
# que cada frase de la respuesta sea fiel. Evaluar también las afirmaciones
# finales y propagar la identidad del usuario a cada herramienta.
#
# Para recordar: catálogo, solicitud y ejecución son piezas distintas;
# los resultados llevan identidad de llamada; los límites están en código.

# %%
def main() -> int:
    args, backend = start("Tool use con herramientas acotadas.",
                          lambda parser: parser.add_argument("--case", choices=("normal", "destructivo"), default="normal"))
    trace = Trace("02_tool_use", backend.name, backend.model)
    try:
        result = run(Llm(backend, trace), trace, args.case)
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    trace.end(completed=True, **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
