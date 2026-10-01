# %% [markdown]
# # RAG avanzado: controlar el recorrido y el contexto
#
# Objetivos: leer las rutas de un grafo LangGraph, separar permisos de
# relevancia y bloquear una respuesta que no pasa la verificación.
# Prerrequisitos: RAG básico, JSON y los dos modelos locales configurados.
# Ejecutar: `python 02_rag\src\02_rag_avanzado.py`.
#
# Qué quitamos: presentación y replay. Conservamos reescritura, recuperación
# híbrida, cuarentena y límites. La implementación del grafo está en
# [rag_graph.py](rag_graph.py); las llamadas y contratos, en
# [advanced_ops.py](advanced_ops.py). No se ejecutan acciones sobre sistemas.

# %%
import json
import sys

from context import valid_citations
from embeddings import Embedder
from model import Llm
from model_config import start
from rag_graph import MAX_GENERATIONS, MAX_SEARCHES, build_graph, run
from retrieval import Index
from settings import ROLES
from trace_log import Trace

DEFAULT_QUESTION = "Un compañero se va del centro, ¿qué pasa con su usuario de GitLab y sus proyectos de código?"


# %% [markdown]
# ## 1. Inspeccionar las rutas antes de ejecutar
#
# `--grafo` muestra Mermaid sin usar modelos. Después de calificar, una
# función decide si genera, busca otra vez o se abstiene. Después de
# verificar, otra decide si termina, regenera o bloquea. El modelo no
# controla esos topes.

# %%
def extra_args(parser):
    parser.add_argument("--pregunta", default=DEFAULT_QUESTION)
    parser.add_argument("--rol", choices=tuple(ROLES), default="analista")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--grafo", action="store_true")
    parser.add_argument("--reindexar", action="store_true")


# %% [markdown]
# ## 2. Observar candidatos, decisiones y cierre
#
# Recuperación aplica permisos antes de ordenar. Relevancia decide si el
# texto contiene el dato pedido. La verificación comprueba citas en código
# y usa un juicio del modelo para la fidelidad, no una prueba de verdad.

# %%
def main() -> int:
    args, backend = start("RAG avanzado con rutas acotadas.", extra_args)
    if args.grafo:
        try:
            print(build_graph(None, None, None, None, args.k).get_graph().draw_mermaid())
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        return 0
    trace = Trace("02_rag_avanzado", backend.name, backend.model)
    try:
        llm, embedder = Llm(backend, trace), Embedder(trace)
        index = Index.build(embedder, force=args.reindexar, trace=trace)
        final = run(args.pregunta, args.rol, llm, embedder, index, trace, args.k)
        assert final["searches"] <= MAX_SEARCHES and final["generations"] <= MAX_GENERATIONS
        hits = final.get("relevant", [])
        assert all(hit.chunk.classification in ROLES[args.rol] and not hit.chunk.quarantined for hit in hits)
        if backend.name != "local":
            assert all(hit.chunk.classification != "reservada" for hit in hits)
        trace.show("Recorrido", " -> ".join(final["path"]))
        trace.show("Contexto final", json.dumps([hit.record() for hit in hits], ensure_ascii=False, indent=2))
        blocked = final["status"] == "bloqueada"
        if blocked:
            trace.show("BLOQUEADA", "No se publica el texto no verificado. Revisar la traza y las fuentes.")
        else:
            trace.show(f"Respuesta ({final['status']})", final["answer"])
            if final["status"] == "verificada":
                assert valid_citations(final["answer"], hits)
        trace.end(completed=not blocked, status=final["status"], respuesta=final["answer"],
                  searches=final["searches"], generations=final["generations"], path=final["path"])
        return 2 if blocked else 0
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2


# %% [markdown]
# ## En producción
#
# El rol debe venir de una identidad autenticada, no de un argumento CLI.
# Evaluar el juez, registrar versiones y aplicar controles de salida a
# preguntas y respuestas. La cuarentena por patrones no garantiza limpieza.
#
# Para recordar: permiso no equivale a relevancia; cita no equivale a
# fidelidad; una respuesta bloqueada no se sustituye por un éxito aparente.

# %%
if __name__ == "__main__":
    raise SystemExit(main())
