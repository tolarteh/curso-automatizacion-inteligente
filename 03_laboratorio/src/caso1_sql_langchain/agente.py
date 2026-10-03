"""El agente SQL del tema 01 con LangChain: un solo ciclo modelo ⇄ herramientas.

En el tema 01 (02_tool_use.py) el ciclo, los topes y el registro de mensajes se escriben
a mano. Aquí `create_agent` arma ese mismo ciclo y los topes son middleware. Lo que NO
cambia: las herramientas y sus controles siguen en sql_readonly.py del tema 01. El permiso
lo decide la herramienta (conexión de solo lectura, tablas y funciones permitidas), no el
prompt ni el framework.
"""
import json

import reuso  # noqa: F401
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from settings import PROMPTS, PROMPTS_01
from sql_readonly import list_tables as _list_tables  # tema 01
from sql_readonly import safe_run  # tema 01: devuelve {"ok": False, "error": "SQL_DENEGADO..."} si no se permite

MAX_TOOL_CALLS = 3    # como en el tema 01
MAX_MODEL_CALLS = 5   # turnos del modelo por pregunta
RECURSION_LIMIT = 40  # red de seguridad: create_agent compila un grafo y cada middleware suma pasos


@tool("list_tables")
def list_tables() -> dict:
    """Esquema y fecha de corte de los pedidos sintéticos."""
    return {"ok": True, **_list_tables()}


@tool("run_sql_readonly")
def run_sql_readonly(sql: str) -> dict:
    """Una consulta de solo lectura, máximo 25 filas."""
    return safe_run(sql)


TOOLS = [list_tables, run_sql_readonly]


def system_prompt() -> str:
    criterio = (PROMPTS_01 / "criterio.txt").read_text(encoding="utf-8").strip()  # tema 01
    return (PROMPTS / "caso1_agente.txt").read_text(encoding="utf-8").strip().replace("{criterio}", criterio)


def crear_agente(llm, checkpointer=None):
    """Arma el agente completo: modelo, herramientas, instrucciones y topes.

    Entrada: llm, un modelo de chat de LangChain (ChatOpenAI hacia Groq, o el doble de las
        pruebas); checkpointer opcional (no se usa en este caso).
    Salida: el agente que devuelve langchain.agents.create_agent. Se usa así:
        agente.invoke({"messages": [...]}, config).
    """
    return create_agent(
        llm, TOOLS, system_prompt=system_prompt(),
        middleware=[ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS, exit_behavior="end"),
                    ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end")],
        checkpointer=checkpointer)


def resultados(messages: list) -> list[dict]:
    """Los resultados de herramientas, como diccionarios, en orden."""
    found = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                content = json.loads(message.content)
            except (TypeError, ValueError):
                content = {"ok": False, "error": str(message.content)}
            found.append({"name": message.name, **(content if isinstance(content, dict) else {"ok": False})})
    return found


def es_limite(messages: list) -> bool:
    """El middleware corta con mensajes propios; Qwen sin herramientas a veces escribe <tool_call>."""
    for message in messages:
        text = str(message.content)
        if isinstance(message, ToolMessage) and text.startswith(("Tool call limit", "Execution stopped")):
            return True
        if isinstance(message, AIMessage) and ("call limit" in text.lower() or "<tool_call>" in text):
            return True
    return False


def preguntar(agente, pregunta: str, *, callbacks=()) -> dict:
    """Hace UNA pregunta al agente y devuelve lo necesario para comprobarla sin usar otro modelo.

    Salida (dict):
        answer: str                 el texto final del modelo
        tool_results: list[dict]    resultados de las herramientas, en orden (usa resultados(messages))
        limite: bool                True si se llegó a un tope (usa es_limite(messages))
        last_rows: list[dict] | None   filas de la última consulta exitosa de run_sql_readonly;
                                    si hay varias, preferir la que tenga justo las columnas
                                    region y retrasados (la forma de la referencia del tema 01)
        model_calls: int            cuántas respuestas del modelo (AIMessage) hubo
    """
    final = agente.invoke({"messages": [{"role": "user", "content": pregunta}]},
                          {"recursion_limit": RECURSION_LIMIT, "callbacks": list(callbacks)})
    messages = final["messages"]
    results = [r for r in resultados(messages) if "ok" in r]
    rows = [r["rows"] for r in results if r["name"] == "run_sql_readonly" and r.get("ok")]
    # Se verifica la última consulta con la forma de la referencia (region, retrasados).
    shaped = [r for r in rows if r and all(set(row) == {"region", "retrasados"} for row in r)]
    answer = messages[-1].content if messages else ""
    return {"answer": answer if isinstance(answer, str) else str(answer), "tool_results": results,
            "limite": es_limite(messages), "last_rows": (shaped or rows)[-1] if rows else None,
            "model_calls": sum(isinstance(m, AIMessage) for m in messages)}
