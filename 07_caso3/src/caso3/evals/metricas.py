"""Métricas puras de las evaluaciones del caso 3, sin modelos ni red.

Objetivo: entender qué mide cada métrica y por qué pass^k es más exigente que pass@k.
Prerrequisitos: contratos de ``caso3.contratos``.
Comando: ``python tests\run_cpu.py`` (ejecuta las pruebas de estas funciones).
Producción: las mismas funciones sirven sobre trazas reales de un sistema desplegado.
"""
from collections import defaultdict
from datetime import date

from caso3.contratos import Clasificacion, Dictamen, Extraccion, Hallazgo, ReglaCitada


# %% Clasificador
def score_classifier(pred: Clasificacion, gold_types: dict[str, str], gold_missing: list[str]) -> dict:
    """Exactitud de tipo sobre la unión de ids (perdidos o extras cuentan como error) y de faltantes."""
    pred_types = {d.id: d.tipo for d in pred.documentos}
    duplicates = len(pred.documentos) - len(pred_types)
    ids = set(gold_types) | set(pred_types)
    hits = sum(1 for i in ids if gold_types.get(i) == pred_types.get(i))
    return {
        "tipo_exactitud": hits / (len(ids) + duplicates) if ids or duplicates else 1.0,
        "faltantes_exactitud": float(set(pred.faltantes) == set(gold_missing)),
    }


# %% Extractor
def score_extractor(pred: list[Extraccion], gold: list[Extraccion]) -> dict:
    """Exactitud campo a campo (monto, fecha, NIT) por doc_id; perdidos, extras y duplicados penalizan."""
    gold_by_id = {e.doc_id: e for e in gold}
    pred_by_id: dict[str, Extraccion] = {}
    duplicates = 0
    for e in pred:
        if e.doc_id in pred_by_id:
            duplicates += 1
        pred_by_id.setdefault(e.doc_id, e)
    fields = {"monto": 0, "fecha": 0, "nit": 0}
    for doc_id, g in gold_by_id.items():
        p = pred_by_id.get(doc_id)
        if p is None:
            continue
        fields["monto"] += p.monto_total == g.monto_total
        fields["fecha"] += p.fecha == g.fecha
        fields["nit"] += p.nit.strip() == g.nit.strip()
    docs = len(set(gold_by_id) | set(pred_by_id)) + duplicates
    result = {f"{name}_exactitud": (hits / docs if docs else 1.0) for name, hits in fields.items()}
    result["exactitud"] = sum(fields.values()) / (3 * docs) if docs else 1.0
    return result


# %% Verificador
def score_verifier(reglas: list[ReglaCitada], expected_source: str, fecha_expediente: date) -> dict:
    """Compara fuente, versión, texto e intervalo completo contra el corpus."""
    from caso3.rag.indexar import indexar

    sources = {r.fuente for r in reglas}
    valid = [f.citar() for f in indexar() if f.norma.vigente(fecha_expediente)]
    return {
        "fuente_correcta": float(sources == {expected_source}),
        "vigencia_correcta": float(bool(reglas) and all(r in valid for r in reglas)),
    }


# %% Auditor
def score_auditor(pred_codes: list[str], gold_codes: list[str]) -> dict:
    """Precisión y exhaustividad de códigos de hallazgo; vacío contra vacío es perfecto."""
    pred, gold = set(pred_codes), set(gold_codes)
    hit = len(pred & gold)
    return {
        "precision": hit / len(pred) if pred else 1.0,
        "recall": hit / len(gold) if gold else 1.0,
    }


# %% Redactor
def score_redactor(
    dictamen: Dictamen, gold_decision: str, input_hallazgos: list[Hallazgo], input_reglas: list[ReglaCitada]
) -> dict:
    """Decisión correcta y preservación de los hallazgos y las citas recibidos."""
    out_codes = {h.codigo for h in dictamen.hallazgos}
    out_sources = {r.fuente for r in dictamen.reglas} | {h.regla.fuente for h in dictamen.hallazgos if h.regla}
    in_codes = {h.codigo for h in input_hallazgos}
    in_sources = {r.fuente for r in input_reglas}
    return {
        "decision_correcta": float(dictamen.decision == gold_decision),
        "hallazgos_preservados": len(in_codes & out_codes) / len(in_codes) if in_codes else 1.0,
        "citas_preservadas": len(in_sources & out_sources) / len(in_sources) if in_sources else 1.0,
    }


# %% E2E
def is_false_advance(decision: str | None, gold_decision: str) -> bool:
    """Falso avance: se propone aprobar cuando lo esperado no era aprobar."""
    return decision == "aprobar" and gold_decision != "aprobar"


def pass_hat_k(successes: list[bool], k: int) -> bool:
    """pass^k: las k corridas deben ser exitosas. Faltar corridas cuenta como fallo."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k debe ser un entero positivo.")
    return len(successes) >= k and all(successes[:k])


def pass_at_k(successes: list[bool]) -> bool:
    """pass@k (alguna corrida exitosa). Solo se expone para contrastarlo con pass^k en las pruebas."""
    return any(successes)


def aggregate_pass_hat_k(runs: list[dict], k: int) -> float:
    """Fracción de expedientes cuyas k repeticiones tuvieron éxito, incluyendo las que fallaron con error."""
    by_case: dict[str, list[bool]] = defaultdict(list)
    for r in runs:
        by_case[r["id"]].append(bool(r["exito"]))
    if not by_case:
        return 0.0
    return sum(pass_hat_k(v, k) for v in by_case.values()) / len(by_case)
