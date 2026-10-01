# %% [markdown]
# # RAG básico: indexar, recuperar y generar
#
# Objetivos: separar las tres etapas, observar la similitud coseno y
# reconocer lo que una búsqueda sin controles deja entrar al contexto.
# Prerrequisitos: Python, vectores y LM Studio con lenguaje y embeddings.
# Ejecutar: `python 02_rag\src\01_rag_basico.py`.
#
# Qué quitamos: colores y replay. Conservamos modelos reales y trazas.
# Este contraste omite permisos y cuarentena, solo sobre datos sintéticos
# y con modelo local. No es una configuración para datos reales.

# %%
import json
import numpy as np

from context import cited_numbers, format_context, is_abstention, valid_citations
from documents import load_documents
from embeddings import Embedder
from model import Llm, read_prompt
from model_config import start
from policy import validate_k
from retrieval import Index, dense_search
from trace_log import Trace

DEFAULT_QUESTION = "¿Cuál es la diferencia máxima entre monto solicitado y pagado en una amortización?"


# %% [markdown]
# ## 1. Recuperar no es responder
#
# Normalizamos documento y pregunta. Su producto escalar es el coseno:
# `score = (d / ||d||) @ (q / ||q||)`. La posición indica cercanía,
# no autoridad de la fuente ni permiso para verla.

# %%
def answer(question: str, llm, embedder, index: Index, k: int = 3) -> dict:
    if llm.backend.name != "local":
        raise ValueError("El RAG básico sin controles solo admite un modelo local.")
    validate_k(k)
    hits = dense_search(index, embedder.embed_query(question), k, role=None)
    text = llm.chat([
        {"role": "system", "content": read_prompt("basico.txt")},
        {"role": "user", "content": f"Pregunta: {question}\nContexto JSON:\n{format_context(hits)}"},
    ], purpose="generar_basico", max_tokens=400)
    return {"respuesta": text, "fragmentos": hits, "abstencion": is_abstention(text),
            "citas_validas": valid_citations(text, hits)}


# %% [markdown]
# ## 2. Hacer visible el contexto y sus límites
#
# El paso sin RAG no tiene una fuente verificable del corpus, aunque su
# respuesta pueda sonar correcta. Las ventanas pueden partir una regla.
# El paso con RAG también puede fallar: recuperar texto no verifica la respuesta.

# %%
def extra_args(parser):
    parser.add_argument("--pregunta", default=DEFAULT_QUESTION)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--fragmentacion", choices=("fijo", "secciones"), default="fijo")
    parser.add_argument("--sin-comparar", action="store_true")
    parser.add_argument("--reindexar", action="store_true")


def main() -> int:
    args, backend = start("RAG básico local sobre datos sintéticos.", extra_args)
    trace = Trace("01_rag_basico", backend.name, backend.model)
    try:
        validate_k(args.k)
        if backend.name != "local":
            raise ValueError("Este laboratorio sin controles solo admite --backend local.")
        trace.show("Límite del laboratorio", "Sin permisos ni cuarentena. Solo datos sintéticos y modelo local.")
        llm, embedder = Llm(backend, trace), Embedder(trace)
        if not args.sin_comparar:
            text = llm.chat([
                {"role": "system", "content": "Responde en español, máximo dos oraciones. "
                 "No asumas políticas que no fueron proporcionadas. Indica qué información te falta."},
                {"role": "user", "content": args.pregunta},
            ], purpose="sin_contexto", max_tokens=400)
            trace.show("Sin RAG, sin fuente verificable del corpus", text)
        index = Index.build(embedder, args.fragmentacion, docs=load_documents(),
                            force=args.reindexar, trace=trace)
        trace.show("Índice", f"{len(index.chunks)} fragmentos, dimensión {index.matrix.shape[1]}.")
        assert np.allclose(np.linalg.norm(index.matrix, axis=1), 1.0)
        result = answer(args.pregunta, llm, embedder, index, args.k)
        hits = result.pop("fragmentos")
        assert 0 < len(hits) <= args.k
        trace.show("Recuperación", json.dumps([hit.record() for hit in hits], ensure_ascii=False, indent=2))
        trace.emit("retrieval", hits=[hit.record() for hit in hits])
        trace.show("Respuesta, sin verificación de fidelidad", result["respuesta"])
        trace.show("Citas", str(sorted(cited_numbers(result["respuesta"]))))
        trace.end(completed=True, hits=len(hits), **result)
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    return 0


# %% [markdown]
# ## En producción
#
# Usar permisos de una identidad autenticada y filtrar antes de recuperar.
# Un índice de vectores no reemplaza la gestión de fuentes ni una evaluación.
# Los roles y la cuarentena del siguiente nivel pertenecen a la aplicación.
#
# Para recordar: el vector ayuda a buscar; el contexto conserva la fuente;
# una cita válida no demuestra que la afirmación sea fiel.

# %%
if __name__ == "__main__":
    raise SystemExit(main())
