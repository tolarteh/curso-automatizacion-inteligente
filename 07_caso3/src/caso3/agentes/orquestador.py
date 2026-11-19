# %% [markdown]
# # Revisión del expediente con Deep Agents
#
# Objetivos: seguir cinco handoffs tipados, limitar revisiones en el estado y
# detener la propuesta antes de la firma humana.
# Prerrequisitos: dependencias raíz, corpus del tema y GROQ_API_KEY.
# Comando: python 07_caso3\src\run_case.py E01
# La ejecución real consume cuota. Las pruebas usan dobles solo desde tests.
#
# %% Construcción y controles del estado
import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

from deepagents import create_deep_agent
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from caso3.agentes.subagentes import READ_ONLY, SCHEMAS, payload, subagentes
from caso3.config import DATA, MAX_ROUNDS, OUTPUTS, PROMPTS, ROOT, create_model, provider, resolve_model_name
from caso3.contratos import Clasificacion, Dictamen, Documento, Extraccion, Hallazgo, Item, Paso, ReglaCitada, Traza
from caso3.herramientas.auditoria import cruzar, field, firmante_requerido
from caso3.herramientas.lectura import cargar_expediente, leer_meta_expediente
from caso3.herramientas.normalizar import normalizar_nit, parse_fecha, parse_monto, plain
from caso3.progreso import Progreso
from caso3.rag.recuperar import norma_vigente, recuperar_regla

ROLES = list(SCHEMAS)
ALLOWED_TOOLS = {"write_todos", "task", "proponer_aprobacion"}


class CaseState(AgentState):
    expediente_id: str
    fecha_expediente: str
    documentos: list[dict]
    fase: str
    planificado: bool
    vueltas: int
    clasificacion: dict
    extracciones: list[dict]
    reglas: list[dict]
    hallazgos: list[dict]
    dictamen: dict | None
    pasos: list[dict]
    firma: dict | None


@dataclass
class ApprovalContext:
    actor: str
    hash: str
    rol: str


def dump(items):
    return [item.model_dump(mode="json") for item in items]


def decision_for(findings):
    if any(h.codigo in {"OCR_REQUERIDO", "INYECCION_DOCUMENTAL", "LIMITE_VUELTAS"} for h in findings):
        return "escalar"
    return "devolver" if any(h.severidad == "bloqueante" for h in findings) else "aprobar"


def digest(verdict):
    return hashlib.sha256(json.dumps(verdict, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def check_extractions(extractions, docs):
    expected = {d.id: d for d in docs if d.tipo in {"cotizacion", "factura"}}
    ids = [e.doc_id for e in extractions]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError("El extractor perdió, duplicó o inventó documentos.")
    for extraction in extractions:
        document = expected[extraction.doc_id]
        text = plain(document.texto)
        if (normalizar_nit(extraction.nit) != normalizar_nit(field(text, "nit"))
                or extraction.monto_total != parse_monto(field(text, "monto"))
                or extraction.fecha != parse_fecha(field(text, "fecha"))):
            raise ValueError(f"Extracción no fiel a la evidencia: {extraction.doc_id}")
        iva = field(text, "iva incluido")
        expected_iva = True if iva == "si" else False if iva == "no" else None
        winner = document.tipo == "cotizacion" and field(text, "ganadora") == "si"
        item_matches = re.findall(r"(?im)^Item:\s*(.*?);\s*cantidad\s+(\d+);\s*valor unitario\s+([^\r\n]+)", document.texto)
        items = [Item(descripcion=name.strip(), cantidad=int(quantity), valor_unitario=parse_monto(amount))
                 for name, quantity, amount in item_matches]
        if (extraction.iva_incluido != expected_iva or extraction.es_ganadora != winner
                or extraction.items != items):
            raise ValueError(f"El extractor alteró IVA, ítems o ganadora: {extraction.doc_id}")


class Control(AgentMiddleware):
    state_schema = CaseState

    def after_model(self, state, runtime):
        if len(state["messages"][-1].tool_calls) > 1:
            raise ValueError("El control exige una sola herramienta por turno.")
        return None

    def wrap_tool_call(self, request, handler):
        state = request.state
        name = request.tool_call["name"]
        if name == "write_todos":
            result = handler(request)
            if not isinstance(result, Command):
                raise ValueError("La planificación no actualizó el estado.")
            return Command(update={**result.update, "planificado": True})
        if name == "proponer_aprobacion":
            if state["fase"] != "propuesta" or not state.get("dictamen"):
                raise ValueError("No se puede proponer sin completar las cinco etapas.")
            return handler(request)
        if name not in ALLOWED_TOOLS:
            # Deep Agents siempre ofrece herramientas de archivos: se deniegan sin ejecutarlas.
            print(f"Control: herramienta denegada al orquestador: {name}", file=sys.stderr)
            return ToolMessage(f"Herramienta no autorizada para el orquestador: {name}. "
                               f"Usa solo {', '.join(sorted(ALLOWED_TOOLS))}.",
                               tool_call_id=request.tool_call["id"], status="error")
        role = request.tool_call["args"]["subagent_type"]
        if not state["planificado"] or role != state["fase"]:
            raise ValueError(f"Handoff fuera de orden; se esperaba {state['fase']}.")
        docs = [Documento.model_validate(d) for d in state["documentos"]]
        when = date.fromisoformat(state["fecha_expediente"])
        context = {key: state.get(key) for key in ("clasificacion", "extracciones", "reglas", "hallazgos", "vueltas")}
        deterministic = []
        if role == "auditor":
            deterministic = cruzar([Extraccion.model_validate(e) for e in state["extracciones"]], docs,
                                  fecha_expediente=when, reglas=[ReglaCitada.model_validate(r) for r in state["reglas"]])
            context["hallazgos"] = dump(deterministic)
        call = {**request.tool_call, "args": {
            "subagent_type": role, "description": payload(docs, when, context),
        }}
        start = time.perf_counter()
        result = handler(request.override(tool_call=call))
        if not isinstance(result, Command) or not isinstance(result.update, dict):
            raise ValueError("El subagente no devolvió un handoff estructurado.")
        message = result.update["messages"][-1]
        output = SCHEMAS[role].model_validate_json(message.content)
        phase = ROLES[ROLES.index(role) + 1] if role != "redactor" else "propuesta"
        updates = {}
        if role == "clasificador":
            original = {d.id: d for d in docs}
            actual = {d.id: d for d in output.documentos}
            if len(actual) != len(output.documentos) or set(actual) != set(original):
                raise ValueError("La clasificación perdió o duplicó documentos.")
            for key, doc in actual.items():
                declared_type = original[key].tipo
                if (doc.ruta != original[key].ruta or doc.texto != original[key].texto
                        or (declared_type != "otro" and doc.tipo != declared_type)
                        or (doc.texto.startswith("OCR_REQUERIDO:") and doc.tipo != "otro")):
                    raise ValueError("Clasificación no fiel a los documentos de entrada.")
            updates["clasificacion"] = output.model_dump(mode="json")
            updates["documentos"] = dump(output.documentos)
        elif role == "extractor":
            check_extractions(output.extracciones, docs)
            updates["extracciones"] = dump(output.extracciones)
        elif role == "verificador":
            expected = recuperar_regla("cotizaciones certificados firma", when)
            if not output.reglas or set(r.model_dump_json() for r in output.reglas) != set(r.model_dump_json() for r in expected):
                raise ValueError("El verificador omitió o alteró las reglas vigentes.")
            updates["reglas"] = dump(output.reglas)
        elif role == "auditor":
            by_code = {h.codigo: h for h in output.hallazgos}
            if len(by_code) != len(output.hallazgos) or any(by_code.get(h.codigo) != h for h in deterministic):
                raise ValueError("El auditor suprimió o modificó un hallazgo determinista.")
            findings = output.hallazgos
            target = next((h.devolver_a for h in findings if h.devolver_a), None)
            if target:
                if state["vueltas"] < MAX_ROUNDS:
                    updates["vueltas"] = state["vueltas"] + 1
                    phase = target
                else:
                    findings = findings + [Hallazgo(codigo="LIMITE_VUELTAS", severidad="bloqueante",
                                                    detalle="Persisten dudas tras dos revisiones.")]
            updates["hallazgos"] = dump(findings)
        else:
            expected_findings = [Hallazgo.model_validate(h) for h in state["hallazgos"]]
            if (output.decision != decision_for(expected_findings) or output.vueltas != state["vueltas"]
                    or output.hallazgos != expected_findings
                    or dump(output.reglas) != state["reglas"]):
                raise ValueError("El redactor cambió la decisión, evidencia, citas o vueltas.")
            updates["dictamen"] = output.model_dump(mode="json")
        step = Paso(agente=role, entrada_resumen=f"{len(docs)} documentos; vuelta {state['vueltas']}",
                    salida_resumen=f"Contrato {type(output).__name__}; siguiente fase {phase}",
                    ms=(time.perf_counter() - start) * 1000)
        # El estado guarda el resultado completo; el orquestador recibe un resumen para no exceder la cuota.
        summary = dict(
            clasificador=lambda: dict(documentos=len(output.documentos), faltantes=output.faltantes),
            extractor=lambda: dict(extracciones=len(output.extracciones)),
            verificador=lambda: dict(reglas=sorted({r.fuente for r in output.reglas})),
            auditor=lambda: dict(hallazgos=[h["codigo"] for h in updates["hallazgos"]]),
            redactor=lambda: dict(decision=output.decision),
        )[role]()
        content = json.dumps(dict(agente=role, contrato=type(output).__name__, validado=True,
                                  resumen=summary, siguiente_fase=phase), ensure_ascii=False)
        return Command(update={**updates, "fase": phase, "pasos": state["pasos"] + [step.model_dump(mode="json")],
                               "messages": [ToolMessage(content, tool_call_id=request.tool_call["id"])]})


@tool
def proponer_aprobacion(runtime: ToolRuntime[ApprovalContext | None]) -> Command:
    """Presenta la propuesta validada y registra la firma solo tras aprobación humana."""
    state = runtime.state
    context = runtime.context
    if state["fase"] != "propuesta" or context is None or not context.actor.strip():
        raise ValueError("Falta la revisión humana identificada.")
    if context.hash != digest(state["dictamen"]):
        raise ValueError("La firma no corresponde al dictamen revisado.")
    winner = next(Extraccion.model_validate(e) for e in state["extracciones"] if e["es_ganadora"])
    role = firmante_requerido(winner.monto_total, norma_vigente(date.fromisoformat(state["fecha_expediente"])))
    if context.rol != role:
        raise ValueError(f"El rol declarado no puede firmar esta cuantía; se requiere {role}.")
    return Command(update={
        "firma": dict(actor=context.actor.strip(), rol=role, hash=context.hash, decision="aceptada"),
        "fase": "firmada",
        "messages": [ToolMessage("Firma humana registrada sobre la propuesta.", tool_call_id=runtime.tool_call_id)],
    })


def construir_agente(model=None):
    model = model if model is not None else create_model()
    return create_deep_agent(
        model=model, tools=[proponer_aprobacion], subagents=subagentes(model),
        system_prompt=(PROMPTS / "orquestador.md").read_text(encoding="utf-8"),
        middleware=[Control()], permissions=READ_ONLY, checkpointer=InMemorySaver(),
        context_schema=ApprovalContext,
        interrupt_on={"proponer_aprobacion": True},
    )


class Tokens(BaseCallbackHandler):
    def __init__(self):
        self.total = 0
        self.known = False

    def on_llm_end(self, response, **kwargs):
        for group in response.generations:
            for generation in group:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if usage:
                    self.total += usage["total_tokens"]
                    self.known = True


@dataclass
class Resultado:
    dictamen: Dictamen
    traza: Traza
    interrumpido: bool
    tokens: int | None
    clasificacion: Clasificacion
    extracciones: list[Extraccion]
    reglas: list[ReglaCitada]
    hallazgos: list[Hallazgo]
    graph: object
    config: dict
    hash: str
    rol_requerido: str
    firma: dict | None = None


def ejecutar_expediente(path: Path, model=None, model_name=None) -> Resultado:
    path = Path(path)
    if not path.is_absolute():
        path = DATA / "expedientes" / path if len(path.parts) == 1 else ROOT / path
    meta = leer_meta_expediente(path)
    docs = cargar_expediente(path, permitir_ocr_pendiente=True)
    model = model if model is not None else create_model(model_name)
    graph = construir_agente(model)
    tokens = Tokens()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80,
              "callbacks": [tokens, Progreso(len(docs), todos_log=OUTPUTS / "logs" / f"{meta['id']}_todos.jsonl")]}
    request = (f"Revisa el expediente {meta['id']} con fecha {meta['fecha']}. Sus {len(docs)} documentos "
               f"({', '.join(d.id for d in docs)}) ya están cargados: los controles se los entregan a cada "
               "subagente, no necesitas pedirlos. Empieza con write_todos y luego delega con task "
               "al clasificador. Al final presenta la propuesta para firma.")
    state = graph.invoke(dict(
        messages=[{"role": "user", "content": request}],
        expediente_id=meta["id"], fecha_expediente=meta["fecha"], documentos=dump(docs),
        fase="clasificador", planificado=False, vueltas=0, clasificacion={}, extracciones=[],
        reglas=[], hallazgos=[], dictamen=None, pasos=[], firma=None,
    ), config)
    interrupts = state.get("__interrupt__", [])
    requests = [r for interrupt in interrupts for r in interrupt.value.get("action_requests", [])]
    if state.get("fase") != "propuesta" or not state.get("dictamen") or len(requests) != 1 or requests[0]["name"] != "proponer_aprobacion":
        raise ValueError("La ejecución no llegó a una propuesta validada con interrupción humana.")
    verdict = Dictamen.model_validate(state["dictamen"])
    trace = Traza(expediente_id=meta["id"], pasos=[Paso.model_validate(p) for p in state["pasos"]], vueltas=state["vueltas"])
    extractions = [Extraccion.model_validate(e) for e in state["extracciones"]]
    winner = next(e for e in extractions if e.es_ganadora)
    role = firmante_requerido(winner.monto_total, norma_vigente(date.fromisoformat(meta["fecha"])))
    return Resultado(verdict, trace, True, tokens.total if tokens.known else None,
                     Clasificacion.model_validate(state["clasificacion"]),
                     extractions,
                     [ReglaCitada.model_validate(r) for r in state["reglas"]],
                     [Hallazgo.model_validate(h) for h in state["hallazgos"]], graph, config, digest(state["dictamen"]), role)


def firmar(result: Resultado, actor: str, aceptar: bool, rol: str | None = None):
    if not actor.strip() or not result.interrumpido or result.firma:
        raise ValueError("La firma requiere actor, interrupción pendiente y ausencia de firma previa.")
    snapshot = result.graph.get_state(result.config)
    if digest(snapshot.values["dictamen"]) != result.hash:
        raise ValueError("La propuesta cambió desde la revisión.")
    if not aceptar:
        result.firma = dict(actor=actor.strip(), hash=result.hash, decision="rechazada")
        result.graph.update_state(result.config, {"fase": "rechazada", "firma": result.firma})
        result.interrumpido = False
        return result.firma
    if rol != result.rol_requerido:
        raise ValueError(f"Se requiere el rol declarado {result.rol_requerido}.")
    state = result.graph.invoke(Command(resume={"decisions": [{"type": "approve"}]}), result.config,
                                context=ApprovalContext(actor=actor, hash=result.hash, rol=rol))
    if state.get("__interrupt__") or not state.get("firma") or state["fase"] != "firmada":
        raise ValueError("La reanudación no registró una firma válida.")
    result.firma = state["firma"]
    result.interrumpido = False
    return result.firma


# %% CLI y estados observables
def main(argv=None):
    parser = argparse.ArgumentParser(description="Revisión de compras con Deep Agents y firma humana.")
    parser.add_argument("expediente", nargs="?", default="E01")
    parser.add_argument("--modelo")
    parser.add_argument("--firmar", action="store_true", help="pedir decisión humana después de mostrar la propuesta")
    args = parser.parse_args(argv)
    print(f"Proveedor: {provider()} | modelo: {resolve_model_name(args.modelo)}")
    result = ejecutar_expediente(Path(args.expediente), model_name=args.modelo)
    print(result.dictamen.model_dump_json(indent=2))
    print(f"Interrupción humana: {result.interrumpido} | vueltas: {result.dictamen.vueltas} | tokens: {result.tokens}")
    print(f"Rol requerido por cuantía: {result.rol_requerido}")
    if args.firmar:
        print("Firma educativa con identidad declarada, sin autenticación externa.")
        actor = input("Identidad del revisor: ")
        role = input("Rol declarado del revisor: ")
        decision = input("Escriba aceptar o rechazar: ").strip()
        if decision not in {"aceptar", "rechazar"}:
            raise ValueError("Decisión humana inválida.")
        print(firmar(result, actor, decision == "aceptar", role.strip()))
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / f"{result.traza.expediente_id}_traza.json").write_text(result.traza.model_dump_json(indent=2), encoding="utf-8")
    (OUTPUTS / f"{result.traza.expediente_id}_dictamen.json").write_text(
        json.dumps(dict(propuesta=result.dictamen.model_dump(mode="json"), firma=result.firma), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


# %% [markdown]
# Producción: autenticar al firmante, persistir checkpoints y aprobaciones de forma
# transaccional, y limitar cuota y concurrencia. InMemorySaver solo vive en este proceso.
if __name__ == "__main__":
    raise SystemExit(main())
