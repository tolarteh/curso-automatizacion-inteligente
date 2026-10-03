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


def list_tables() -> dict:
    """TODO(caso 1): el modelo lee este texto para saber para qué sirve la herramienta. Reescríbelo."""
    # TODO(caso 1 · herramienta list_tables). Conviértela en una herramienta de LangChain llamada
    # "list_tables", sin argumentos, que devuelva {"ok": True, ...esquema y fecha de corte...}.
    # Decide qué descripción lee el modelo. El esquema ya existe en el tema 01 (_list_tables).
    raise NotImplementedError("Caso 1 · agente.list_tables: crea la herramienta (nombre, descripción "
                              "para el modelo y qué devuelve).")


def run_sql_readonly(sql: str) -> dict:
    """TODO(caso 1): el modelo lee este texto para saber para qué sirve la herramienta. Reescríbelo."""
    # TODO(caso 1 · herramienta run_sql_readonly + barrera de seguridad). Conviértela en una
    # herramienta de LangChain llamada "run_sql_readonly" con un solo argumento obligatorio: `sql`.
    # Decide DÓNDE vive el permiso. El prompt pide no borrar, pero ¿qué impide de verdad un
    # DELETE, un DROP, un ATTACH o un PRAGMA? Mira safe_run (importado arriba, del tema 01):
    # qué revisa y qué devuelve cuando no permite una consulta. Lo que debe devolver la herramienta:
    #   si funciona  → {"ok": True, "rows": [...], "truncated": bool}
    #   si se niega  → {"ok": False, "error": "SQL_DENEGADO: ..."}   (o SQL_INVALIDO / SQL_TIMEOUT)
    # Si usas safe_run, llámalo por su nombre en este módulo: las pruebas lo cambian por una base
    # temporal. Puedes sumar tu propio filtro antes, como capa extra.
    raise NotImplementedError("Caso 1 · agente.run_sql_readonly: crea la herramienta de consulta y decide "
                              "qué parte del código rechaza el SQL que escribe o borra.")


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
    # TODO(caso 1 · create_agent). Decide:
    #   - Qué herramientas recibe (TOOLS) y qué instrucciones (system_prompt(), que lee
    #     prompts/caso1_agente.txt; ese archivo también tiene un TODO).
    #   - Los topes. En LangChain se ponen como middleware: piezas que se meten en el ciclo
    #     del agente y lo vigilan (ya están importadas). Máximo MAX_TOOL_CALLS herramientas y
    #     MAX_MODEL_CALLS llamadas al modelo por pregunta.
    #   - Qué pasa al llegar al tope: ¿un error o un final ordenado? (busca exit_behavior en la
    #     documentación de LangChain 1.x).
    raise NotImplementedError("Caso 1 · agente.crear_agente: arma create_agent con herramientas, "
                              "instrucciones y topes (middleware).")


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
    # TODO(caso 1 · usar el agente). Decide cómo llamarlo (el mensaje del usuario, los callbacks y
    # RECURSION_LIMIT en la configuración) y cómo pasar de la lista final de mensajes a la salida
    # de arriba. Lo que se comprueba son las filas que devolvió la herramienta, no el texto.
    raise NotImplementedError("Caso 1 · agente.preguntar: llama al agente y saca la respuesta, los resultados "
                              "de las herramientas, el tope y las filas para comprobar.")
