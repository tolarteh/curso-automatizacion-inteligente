"""Grafo acotado: el modelo propone; las rutas y los topes pertenecen al código."""
import operator
import os
from typing import Annotated, TypedDict

from advanced_ops import grade, lexical_query, rewrite, verify
from context import format_context, is_abstention
from hybrid import hybrid_search
from model import read_prompt
from policy import validate_k
from retrieval import Hit
from settings import NO_EVIDENCE, ROLES

MAX_SEARCHES = 2
MAX_GENERATIONS = 2


class State(TypedDict, total=False):
    question: str
    role: str
    query: str
    keywords: list[str]
    candidates: list[Hit]
    relevant: list[Hit]
    searches: int
    generations: int
    answer: str | None
    verification: dict
    status: str
    path: Annotated[list[str], operator.add]


def disable_external_tracing() -> None:
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        if os.environ.get(name, "").strip().lower() not in ("", "false", "0", "off"):
            raise ValueError(f"{name} debe estar desactivado: las trazas de este laboratorio son locales.")
        os.environ.setdefault(name, "false")


def build_graph(llm, embedder, index, trace, k: int = 6, *, remote: bool = False):
    validate_k(k)
    disable_external_tracing()
    from langgraph.graph import END, START, StateGraph

    def mark(name: str, **data):
        trace.emit("node", name=name, **data)
        return {"path": [name]}

    def rewrite_node(state: State):
        previous = state.get("query", "")
        result = rewrite(llm, state["question"], previous)
        return {"query": result["consulta"], "keywords": result["palabras_clave"],
                "searches": state["searches"] + 1, **mark("reescribir", result=result)}

    def retrieve_node(state: State):
        rewritten = {"consulta": state["query"], "palabras_clave": state["keywords"]}
        hits = hybrid_search(index, embedder, state["query"], lexical_query(state["question"], rewritten),
                             k, role=state["role"], remote=remote)
        return {"candidates": hits, **mark("recuperar", hits=[hit.record() for hit in hits])}

    def grade_node(state: State):
        relevant = grade(llm, state["question"], state["candidates"])
        return {"relevant": relevant, **mark("calificar", kept=[hit.chunk.id for hit in relevant])}

    def generate_node(state: State):
        problems = state.get("verification", {}).get("problemas", [])
        text = llm.chat([
            {"role": "system", "content": read_prompt("generar.txt")},
            {"role": "user", "content": f"Pregunta: {state['question']}\n"
             f"Contexto JSON:\n{format_context(state['relevant'])}\n"
             f"Problemas que debes corregir: {problems}"},
        ], purpose="generar", max_tokens=500)
        return {"answer": text, "generations": state["generations"] + 1, **mark("generar")}

    def verify_node(state: State):
        text = state["answer"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("No se recibió una respuesta para verificar.")
        if is_abstention(text):
            verdict = {"sustentada": True, "problemas": []}
            status = "sin_evidencia"
        else:
            verdict = verify(llm, state["question"], text, state["relevant"])
            status = "verificada" if verdict["sustentada"] else "pendiente"
        return {"verification": verdict, "status": status, **mark("verificar", verdict=verdict)}

    def abstain_node(state: State):
        return {"answer": NO_EVIDENCE, "status": "sin_evidencia", "relevant": [], **mark("abstenerse")}

    def block_node(state: State):
        return {"answer": None, "status": "bloqueada", **mark("bloquear", verdict=state["verification"])}

    def after_grade(state: State):
        if state["relevant"]:
            return "generar"
        return "reescribir" if state["searches"] < MAX_SEARCHES else "abstenerse"

    def after_verify(state: State):
        if state["verification"]["sustentada"]:
            return "fin"
        return "generar" if state["generations"] < MAX_GENERATIONS else "bloquear"

    graph = StateGraph(State)
    nodes = {"reescribir": rewrite_node, "recuperar": retrieve_node, "calificar": grade_node,
             "generar": generate_node, "verificar": verify_node, "abstenerse": abstain_node,
             "bloquear": block_node}
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.add_edge(START, "reescribir")
    graph.add_edge("reescribir", "recuperar")
    graph.add_edge("recuperar", "calificar")
    graph.add_conditional_edges("calificar", after_grade,
                                {name: name for name in ("generar", "reescribir", "abstenerse")})
    graph.add_edge("generar", "verificar")
    graph.add_conditional_edges("verificar", after_verify,
                                {"generar": "generar", "bloquear": "bloquear", "fin": END})
    graph.add_edge("abstenerse", END)
    graph.add_edge("bloquear", END)
    return graph.compile()


def run(question: str, role: str, llm, embedder, index, trace, k: int = 6) -> State:
    if role not in ROLES or not isinstance(question, str) or not question.strip():
        raise ValueError("Se necesita un rol conocido y una pregunta no vacía.")
    app = build_graph(llm, embedder, index, trace, k, remote=llm.backend.name == "groq")
    return app.invoke({"question": question, "role": role, "path": [], "searches": 0, "generations": 0})
