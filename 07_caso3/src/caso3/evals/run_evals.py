# %% [markdown]
# # Medir componentes y punta a punta
#
# Objetivos: aislar errores de cada agente y medir pass^k y falsos avances.
# Prerrequisitos: corpus, dependencias raíz y GROQ_API_KEY. Consume cuota real.
# Comando: python 07_caso3\src\run_evals.py -k 3 --solo-agente e2e
# Estados observables: fila por intento, resumen, CSV y Traza por corrida.
#
# %% Insumos y ejecución
import argparse
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
import sys
import time

from caso3.config import DATA, OUTPUTS, provider, resolve_model_name
from caso3.contratos import Extraccion, Paso, Traza
from caso3.evals import metricas

AGENTS = ("clasificador", "extractor", "verificador", "auditor", "redactor", "e2e")


def load_golden(path=None):
    rows = [json.loads(line) for line in (path or DATA / "golden.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r"E\d{2}", key) for key in ids):
        raise ValueError("Golden vacío, duplicado o con identificadores inválidos.")
    return rows


def safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value) or "modelo"


def gold_extractions(case):
    return [Extraccion.model_validate(e) for e in case["extracciones_esperadas"]]


def gold_rules(case):
    from caso3.rag.recuperar import recuperar_regla
    return recuperar_regla("cotizaciones certificados firma", date.fromisoformat(case["fecha"]))


def gold_findings(case):
    from caso3.herramientas.auditoria import cruzar
    from caso3.herramientas.lectura import cargar_expediente
    findings = cruzar(gold_extractions(case), cargar_expediente(DATA / "expedientes" / case["id"], permitir_ocr_pendiente=True),
                      fecha_expediente=date.fromisoformat(case["fecha"]), reglas=gold_rules(case))
    if {h.codigo for h in findings} != set(case["hallazgos_esperados"]):
        raise ValueError("El insumo dorado del redactor no coincide con los hallazgos anotados.")
    return findings


def build_context(agent, case, docs):
    dump = lambda values: [v.model_dump(mode="json") for v in values]
    ctx = {}
    if agent != "clasificador":
        ctx["clasificacion"] = dict(documentos=dump(docs), faltantes=case["documentos_faltantes"])
    if agent in {"verificador", "auditor", "redactor"}:
        ctx["extracciones"] = dump(gold_extractions(case))
    if agent in {"auditor", "redactor"}:
        ctx["reglas"] = dump(gold_rules(case))
        ctx["hallazgos"] = dump(gold_findings(case))
    ctx["vueltas"] = 0
    return ctx


@dataclass
class Medicion:
    respuesta: object
    traza: Traza
    tokens: int | None


def default_runner(agent, case, model_name):
    from caso3.agentes.orquestador import ejecutar_expediente
    from caso3.agentes.subagentes import ejecutar_subagente
    from caso3.herramientas.lectura import cargar_expediente
    path = DATA / "expedientes" / case["id"]
    if agent == "e2e":
        return ejecutar_expediente(path, model_name=model_name)
    docs = cargar_expediente(path, permitir_ocr_pendiente=True)
    inputs = [d.model_copy(update={"tipo": "otro"}) for d in docs] if agent == "clasificador" else docs
    start = time.perf_counter()
    response = ejecutar_subagente(agent, inputs, date.fromisoformat(case["fecha"]), model_name=model_name,
                                  contexto=build_context(agent, case, docs))
    trace = Traza(expediente_id=case["id"], vueltas=0, pasos=[Paso(
        agente=agent, entrada_resumen=f"{len(docs)} documentos; insumos de predecesores dorados",
        salida_resumen=type(response).__name__, ms=(time.perf_counter() - start) * 1000)])
    return Medicion(response, trace, None)


def score(agent, case, result):
    if agent == "clasificador":
        return metricas.score_classifier(result, case["documentos_esperados"], case["documentos_faltantes"])
    if agent == "extractor":
        return metricas.score_extractor(result.extracciones, gold_extractions(case))
    if agent == "verificador":
        return metricas.score_verifier(result.reglas, case["regla_esperada"], date.fromisoformat(case["fecha"]))
    if agent == "auditor":
        return metricas.score_auditor([h.codigo for h in result.hallazgos], case["hallazgos_esperados"])
    if agent == "redactor":
        return metricas.score_redactor(result, case["decision_esperada"], gold_findings(case), gold_rules(case))
    if not result.interrumpido:
        raise ValueError("La evaluación E2E exige interrupción humana, sin firma automática.")
    return dict(decision_correcta=float(result.dictamen.decision == case["decision_esperada"]),
                hallazgos_exactos=float({h.codigo for h in result.dictamen.hallazgos} == set(case["hallazgos_esperados"])))


# %% Repeticiones y trazas
def run_evals(agent, k, model_name, golden, runner=default_runner, out_dir=None, today=None):
    if agent not in AGENTS or isinstance(k, bool) or not isinstance(k, int) or k < 1 or not golden:
        raise ValueError("Se requiere agente conocido, golden no vacío y k entero positivo.")
    out_dir = Path(out_dir) if out_dir is not None else OUTPUTS / "evals"
    trace_dir = out_dir / "trazas" / safe_name(model_name) / agent
    trace_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in golden:
        if not re.fullmatch(r"E\d{2}", case["id"]):
            raise ValueError("Identificador inseguro en golden.")
        for rep in range(1, k + 1):
            start = time.perf_counter()
            trace = Traza(expediente_id=case["id"], pasos=[], vueltas=0)
            row = dict(id=case["id"], rep=rep, agente=agent, modelo=model_name, exito=False,
                       error="", falso_avance=None, vueltas=None, latencia_ms=None, tokens=None)
            try:
                measured = runner(agent, case, model_name)
                result = measured.respuesta if isinstance(measured, Medicion) else measured
                trace = measured.traza if hasattr(measured, "traza") else trace
                row["tokens"] = getattr(measured, "tokens", None)
                if agent == "e2e":
                    row["falso_avance"] = metricas.is_false_advance(result.dictamen.decision, case["decision_esperada"])
                metrics = score(agent, case, result)
                row.update(metrics)
                row["exito"] = all(value == 1 for value in metrics.values())
                row["vueltas"] = trace.vueltas
            except Exception as exc:
                # Cada fallo queda visible en consola y CSV, y cuenta como fallo en pass^k.
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"ERROR {case['id']} intento {rep}: {row['error']}", file=sys.stderr)
            row["latencia_ms"] = (time.perf_counter() - start) * 1000
            (trace_dir / f"{case['id']}_r{rep}.json").write_text(json.dumps(dict(
                modelo=model_name, agente=agent, intento=rep, error=row["error"],
                traza=trace.model_dump(mode="json")), ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append(row)
    path = out_dir / f"{(today or date.today()).isoformat()}_{safe_name(model_name)}_{agent}.csv"
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows, path


def summarize(rows, k):
    evaluated = [r for r in rows if r["falso_avance"] is not None]
    metrics = {key for row in rows for key in row if key not in {
        "id", "rep", "agente", "modelo", "exito", "error", "falso_avance", "vueltas", "latencia_ms", "tokens"}}
    known_tokens = [r["tokens"] for r in rows if r["tokens"] is not None]
    known_rounds = [r["vueltas"] for r in rows if r["vueltas"] is not None]
    return dict(corridas=len(rows), errores=sum(bool(r["error"]) for r in rows),
                **{f"pass^{k}": metricas.aggregate_pass_hat_k(rows, k)},
                **{key: sum(r.get(key, 0) for r in rows) / len(rows) for key in sorted(metrics)},
                corridas_evaluables=len(evaluated),
                falsos_avances=sum(r["falso_avance"] for r in evaluated) if evaluated else None,
                tokens_promedio=sum(known_tokens) / len(known_tokens) if known_tokens else None,
                corridas_con_tokens=len(known_tokens),
                vueltas_promedio=sum(known_rounds) / len(known_rounds) if known_rounds else None,
                latencia_ms=sum(r["latencia_ms"] for r in rows) / len(rows) if rows else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evals reales del caso 3 con el proveedor de MODEL_PROVIDER.")
    parser.add_argument("-k", type=int, default=3)
    parser.add_argument("--modelo", help="Por defecto GROQ_MODEL o LOCAL_MODEL según el proveedor.")
    parser.add_argument("--solo-agente", choices=AGENTS, default="e2e")
    parser.add_argument("--caso", action="append", help="Evaluar solo estos expedientes, por ejemplo --caso E01.")
    args = parser.parse_args(argv)
    if args.k < 1:
        parser.error("k debe ser positivo.")
    golden = load_golden()
    if args.caso:
        unknown = set(args.caso) - {case["id"] for case in golden}
        if unknown:
            parser.error(f"Casos inexistentes en golden: {', '.join(sorted(unknown))}")
        golden = [case for case in golden if case["id"] in args.caso]
    model_name = resolve_model_name(args.modelo)
    print(f"Proveedor: {provider()} | modelo: {model_name}")
    rows, path = run_evals(args.solo_agente, args.k, model_name, golden)
    print("Métrica                 Valor")
    for key, value in summarize(rows, args.k).items():
        print(f"{key:24} {value}")
    print(f"CSV: {path}")
    return int(any(row["error"] or not row["exito"] for row in rows))


# %% [markdown]
# Producción: separar conjuntos de desarrollo y evaluación, presupuestar tokens
# y conservar versiones de corpus, prompts y modelo junto a cada medición.
if __name__ == "__main__":
    raise SystemExit(main())
