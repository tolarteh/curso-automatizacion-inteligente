# %% [markdown]
# # Evaluar recuperación antes de culpar al generador
#
# Objetivos: calcular acierto y MRR, distinguir recuperación de generación
# y medir exposición de fuentes no autorizadas.
# Prerrequisitos: las dos lecciones anteriores y el modelo de embeddings.
# Ejecutar: `python 02_rag\src\03_evaluacion.py`.
#
# Qué quitamos: tablas de colores y resultados de corridas anteriores.
# Conservamos etiquetas independientes y evaluación por pregunta.
# El comando por defecto usa embeddings reales, no un modelo de lenguaje.

# %%
import importlib
import json
from datetime import datetime, timezone

from documents import load_questions
from embeddings import Embedder
from evaluation import evaluate_retrieval, judge_answer, rank_metrics
from model import Llm
from model_config import start
from rag_graph import run
from retrieval import Index
from settings import OUTPUTS
from trace_log import Trace


# %% [markdown]
# ## 1. Una métrica pequeña que podemos verificar a mano
#
# Con posiciones [1, 3, ausente, 5], acierto@1 es 1/4 y acierto@3 es 2/4.
# MRR@5 es `(1 + 1/3 + 0 + 1/5) / 4`. El ausente cuenta en el denominador.
# Tenemos una frase de evidencia por pregunta, no etiquetas exhaustivas
# de todos los fragmentos relevantes: por eso lo llamamos hit@k.

# %%
hand = rank_metrics([1, 3, None, 5])
assert hand["hit@1"] == 0.25 and hand["hit@3"] == 0.5
assert abs(hand["mrr@5"] - (1 + 1 / 3 + 1 / 5) / 4) < 1e-12


# %% [markdown]
# ## 2. Comparar configuraciones sobre las mismas etiquetas
#
# A: fijo+denso sin filtros, B: secciones+denso, C: secciones+BM25,
# D: secciones+híbrido. B a D filtran permisos y cuarentena.
# E, opcional, añade reescritura; usa el modelo y puede variar entre corridas.

# %%
def evaluate_answers(questions, which: str, llm, embedder, fixed, sections, trace) -> dict:
    basic = importlib.import_module("01_rag_basico")
    names = ["basico", "avanzado"] if which == "ambos" else [which]
    report = {}
    for name in names:
        results = []
        for question in questions:
            if name == "basico":
                outcome = basic.answer(question["pregunta"], llm, embedder, fixed)
                text, hits = outcome["respuesta"], outcome["fragmentos"]
            else:
                outcome = run(question["pregunta"], question["rol"], llm, embedder, sections, trace)
                text, hits = outcome["answer"], outcome.get("relevant", [])
            ok, reason = judge_answer(question, text, hits)
            row = {"id": question["id"], "ok": ok, "reason": reason, "respuesta": text}
            results.append(row)
            trace.emit("evaluation_answer", pipeline=name, **row)
        report[name] = {"total": len(results), "ok": sum(row["ok"] for row in results), "results": results}
    return report


def extra_args(parser):
    parser.add_argument("--reescritura", action="store_true")
    parser.add_argument("--respuestas", choices=("no", "basico", "avanzado", "ambos"), default="no")
    parser.add_argument("--sin-prefijos", action="store_true")
    parser.add_argument("--reindexar", action="store_true")


def main() -> int:
    args, backend = start("Evaluación por componentes sobre 15 preguntas.", extra_args)
    trace = Trace("03_evaluacion", backend.name, backend.model)
    try:
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        report_path = OUTPUTS / "evaluation_result.json"
        report = {"completed": False, "started": datetime.now(timezone.utc).isoformat(),
                  "model": backend.model, "language_model_used": args.reescritura or args.respuestas != "no"}
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        if backend.name != "local" and args.respuestas in ("basico", "ambos"):
            raise ValueError("La evaluación del básico sin controles solo admite modelo local.")
        embedder = Embedder(trace)
        if args.sin_prefijos:
            embedder.doc_prefix = embedder.query_prefix = ""
            trace.show("Experimento", "Se omiten explícitamente los prefijos de Nomic.")
        fixed = Index.build(embedder, "fijo", force=args.reindexar, trace=trace)
        sections = Index.build(embedder, force=args.reindexar, trace=trace)
        questions = load_questions()
        llm = Llm(backend, trace) if args.reescritura or args.respuestas != "no" else None
        retrieval = evaluate_retrieval(questions, embedder, fixed, sections, trace,
                                       llm if args.reescritura else None, remote=backend.name != "local")
        for name in ("B", "C", "D"):
            assert retrieval["summary"][name]["fugas"] == 0
            assert retrieval["summary"][name]["externos"] == 0
        trace.show("Recuperación", json.dumps(retrieval, ensure_ascii=False, indent=2))
        answers = {} if args.respuestas == "no" else evaluate_answers(
            questions, args.respuestas, llm, embedder, fixed, sections, trace)
        if answers:
            trace.show("Respuestas", json.dumps({name: {"ok": result["ok"], "total": result["total"]}
                                                for name, result in answers.items()}, ensure_ascii=False))
        report.update(completed=True, embedding_model=embedder.model,
                      doc_prefix=embedder.doc_prefix, query_prefix=embedder.query_prefix,
                      retrieval=retrieval, answers=answers)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        trace.end(completed=True, retrieval=retrieval["summary"], answers_evaluated=bool(answers))
        return 0
    except (ValueError, AssertionError, OSError) as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2


# %% [markdown]
# ## En producción
#
# Evaluar preguntas de usuarios y medir relevancia por documento y sección.
# Separar abstenciones correctas, respuestas bloqueadas y errores de API.
# Calibrar el juez con revisión humana; palabras clave no sustituyen esa revisión.
#
# Para recordar: medir por componentes, conservar el denominador y
# no confundir una mejora medida en este corpus con una garantía general.

# %%
if __name__ == "__main__":
    raise SystemExit(main())
