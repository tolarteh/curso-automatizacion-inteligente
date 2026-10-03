# %% [markdown]
# # Caso 1: el asistente SQL de solo lectura con LangChain (create_agent)
#
# Objetivos: comparar el ciclo escrito a mano del tema 01 (02_tool_use.py) con el mismo
# agente en ~20 líneas de LangChain, y comprobar que el permiso sigue en la herramienta.
# Por qué LangChain aquí: es un solo ciclo modelo ⇄ herramientas, sin pausas ni ramas de
# negocio. Un framework de alto nivel basta; un grafo explícito sería más código sin ganancia.
# Ejecutar desde la raíz:
# `python 03_laboratorio\src\02_caso1_sql.py --backend groq`
# `python 03_laboratorio\src\02_caso1_sql.py --backend groq --caso destructivo`

# %%
import json

import openai
from langgraph.errors import GraphRecursionError

import comun
from caso1_sql_langchain.agente import MAX_TOOL_CALLS, crear_agente, preguntar, run_sql_readonly
from lesson_utils import evaluate_rows  # tema 01: compara con expected.json
from settings import DATABASE, PROMPTS_01
from trazas_lc import Trace, TraceCallback

DESTRUCTIVO = "Borra los pedidos cancelados de la base."


# %% [markdown]
# ## 1. El agente completo (ver caso1_sql_langchain/agente.py)
#
#     agente = create_agent(llm, [list_tables, run_sql_readonly], system_prompt=...,
#                           middleware=[ToolCallLimitMiddleware(run_limit=3, exit_behavior="end"),
#                                       ModelCallLimitMiddleware(run_limit=5, exit_behavior="end")])
#
# ## 2. La comprobación no depende del modelo

# %%
def run(agente, trace, caso: str) -> dict:
    question = (PROMPTS_01 / "pedido.txt").read_text(encoding="utf-8").strip() if caso == "normal" else DESTRUCTIVO
    trace.show("Pregunta", question)
    try:
        result = preguntar(agente, question, callbacks=[TraceCallback(trace, "caso1")])
    except openai.BadRequestError as exc:
        if not comun.is_tool_use_failed(exc):
            raise
        raise ValueError(f"LIMITE: el modelo insistió en otra herramienta ({MAX_TOOL_CALLS} máximo).") from exc
    for item in result["tool_results"]:
        trace.show(f"Resultado de {item['name']}", json.dumps(item, ensure_ascii=False)[:600])
    trace.show("Respuesta del modelo", result["answer"])
    if result["limite"]:
        raise ValueError(f"LIMITE: máximo {MAX_TOOL_CALLS} llamadas a herramientas por pregunta.")
    if caso == "normal":
        assert result["last_rows"] is not None, "No hubo una consulta verificable."
        passed, reason = evaluate_rows(result["last_rows"])
        trace.show("Comprobación de las filas", reason)
        assert passed, reason
    else:
        probe = run_sql_readonly.invoke({"sql": "DELETE FROM orders WHERE status = 'cancelado'"})
        count = run_sql_readonly.invoke({"sql": "SELECT COUNT(*) AS pedidos FROM orders"})
        trace.show("Prueba directa del rechazo", json.dumps(probe, ensure_ascii=False))
        assert not probe["ok"] and "SQL_DENEGADO" in probe["error"]
        assert count["rows"] == [{"pedidos": 26}], "La base cambió."
    return {"tool_calls": len(result["tool_results"]), "model_calls": result["model_calls"], "verified": True,
            "case": caso}


def main() -> int:
    parse = comun.parser("Caso 1: asistente SQL de solo lectura con langchain.agents.create_agent.")
    parse.add_argument("--caso", choices=("normal", "destructivo"), default="normal")
    args = parse.parse_args()
    if not DATABASE.is_file():
        parse.error("Falta la base sintética. Ejecuta python 01_patrones_agenticos\\src\\seed.py")
    backend = comun.backend_from(args, parse)
    agente = crear_agente(comun.chat_model(backend))
    trace = Trace("03_caso1_sql", backend.name, backend.model)
    try:
        result = run(agente, trace, args.caso)
    except (ValueError, AssertionError, OSError, GraphRecursionError, openai.OpenAIError) as exc:
        trace.show("ERROR", comun.explain(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    trace.end(completed=True, **result)
    return 0


if __name__ == "__main__":
    raise SystemExit(comun.ejecutar(main))
