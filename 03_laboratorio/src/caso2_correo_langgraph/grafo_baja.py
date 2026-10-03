"""El grafo del caso 2: enrutamiento, controles en código y aprobación humana con interrupt.

    START → clasificar ─┬─ irrelevante ──────────────────────────────→ archivar → END
                        └─ otra categoría → extraer → validar ─┬─ BLOQUEAR ──────────→ bloquear → END
                                                               ├─ PEDIR_INFORMACION ─→ pedir_informacion → END
                                                               └─ PLANIFICAR → planificar → aprobar ⟲
    aprobar (interrupt, una vez por rol) ─┬─ falta un rol ──→ aprobar
                                          ├─ alguien dice n → rechazar → END
                                          └─ dos aprobaciones → ejecutar → verificar → END

El modelo solo interviene en clasificar y extraer. Lo que se puede ejecutar, quién debe
aprobar y cómo se comprueba el resultado son nodos y reglas en Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from .git_provider import GitError, verificar_baja
from .politica import (ACCIONES_PERMITIDAS, APROBACIONES_REQUERIDAS, REMITENTES_AUTORIZADOS, evaluar,
                       planificar, validar_aprobacion)

RECURSION_LIMIT = 20
# Finales posibles de un hilo (state["resultado"]). PENDIENTE_APROBACION no es un final: es la pausa.
RESULTADOS = ("IGNORADO", "BLOQUEADO", "PIDE_INFORMACION", "RECHAZADO", "EJECUTADO", "VERIFICACION_FALLIDA")


class Estado(TypedDict, total=False):
    correo: dict
    ruta: dict
    datos: dict
    evaluacion: dict
    plan: dict
    aprobaciones: list
    ejecucion: list
    verificacion: dict
    resultado: str      # IGNORADO | BLOQUEADO | PIDE_INFORMACION | RECHAZADO | EJECUTADO | VERIFICACION_FALLIDA
    respuesta: str      # borrador para responder al remitente (nunca se envía solo)


@dataclass
class Contexto:
    """Dependencias de la ejecución: no se guardan en el checkpoint."""
    git: Any                    # GitProvider
    talento: dict               # radicados del sistema de Talento Humano simulado
    extractor: Any = None       # LlmExtractor; no hace falta para aprobar o rechazar
    remitentes: frozenset = REMITENTES_AUTORIZADOS


def pendientes(state: Estado) -> list[str]:
    hechos = {item["rol"] for item in state.get("aprobaciones", []) if item["decision"] == "s"}
    return [rol for rol in APROBACIONES_REQUERIDAS if rol not in hechos]


def _extractor(runtime: Runtime[Contexto]):
    if runtime.context.extractor is None:
        raise RuntimeError("Este paso necesita el modelo: ejecuta el trigger con --backend.")
    return runtime.context.extractor


# -- Nodos con modelo: el LLM propone ------------------------------------------------------
def clasificar(state: Estado, runtime: Runtime[Contexto]) -> dict:
    return {"ruta": _extractor(runtime).clasificar(state["correo"])}


def extraer(state: Estado, runtime: Runtime[Contexto]) -> dict:
    return {"datos": _extractor(runtime).extraer(state["correo"])}


# -- Nodos en código: el código decide ------------------------------------------------------
def validar(state: Estado, runtime: Runtime[Contexto]) -> dict:
    return {"evaluacion": evaluar(state["correo"], state["ruta"], state["datos"],
                                  runtime.context.talento, runtime.context.git,
                                  runtime.context.remitentes)}


def archivar(state: Estado) -> dict:
    return {"resultado": "IGNORADO"}


def bloquear(state: Estado) -> dict:
    motivos = "\n".join(f"- {item}" for item in state["evaluacion"]["hallazgos"])
    return {"resultado": "BLOQUEADO", "respuesta": (
        f"Asunto: RE: {state['correo']['asunto']}\n\nLa solicitud no se tramita porque incluye "
        f"acciones o condiciones fuera del procedimiento PR-TIC-004:\n{motivos}\n\n"
        "No se ejecutó ningún cambio. El caso se escala a seguridad de la información.")}


def pedir_informacion(state: Estado) -> dict:
    faltan = "\n".join(f"- {item}" for item in state["evaluacion"]["faltantes"])
    return {"resultado": "PIDE_INFORMACION", "respuesta": (
        f"Asunto: RE: {state['correo']['asunto']}\n\nPara iniciar la desvinculación según "
        f"PR-TIC-004 necesitamos:\n{faltan}\n\nSin radicado no se inicia el proceso. "
        "No se ejecutó ningún cambio.")}


def planear(state: Estado, runtime: Runtime[Contexto]) -> dict:
    evaluacion = state["evaluacion"]
    return {"plan": planificar(evaluacion["usuario"], evaluacion["registro"]["jefe_inmediato"],
                               runtime.context.git), "aprobaciones": []}


# -- Aprobación humana ----------------------------------------------------------------------
def aprobar(state: Estado) -> dict:
    """Aprobación humana: el grafo se detiene hasta que una persona decide. Una vez por cada rol.

    Para detenerse se usa interrupt (langgraph.types.interrupt): pausa el grafo, guarda el estado
    en el checkpointer (la «memoria en disco» del grafo) y espera. Se continúa con
    Command(resume=respuesta), aunque pasen días o se reinicie el programa.

    Lo que ve quien aprueba (el valor que se pasa a interrupt) es un dict con, al menos:
        tipo="aprobacion", asunto, radicado, usuario, nombre, jefe_inmediato (estos tres según
        Talento Humano, en state["evaluacion"]["registro"]), repos_mencionados (del correo), plan,
        pendientes (pendientes(state)) y aprobaciones (las que ya hay).
    trigger.decidir(...) y trigger.mostrar(...) leen esas claves; "pendientes" es obligatoria.
    Cuando la persona responde, la respuesta se valida con validar_aprobacion(respuesta, pendientes)
    y se AGREGA a state["aprobaciones"].
    Devuelve: {"aprobaciones": [...las anteriores, la nueva]}.
    """
    # TODO(caso 2 · aprobación humana). Decide dónde se detiene el grafo, qué ve la persona que
    # aprueba y qué se guarda cuando responde. Ojo: al continuar, este nodo se vuelve a ejecutar
    # desde el principio; lo que pongas antes del interrupt corre dos veces.
    raise NotImplementedError("Caso 2 · grafo_baja.aprobar: detén el grafo con interrupt para la aprobación "
                              "humana y guarda la respuesta ya validada.")


def rechazar(state: Estado) -> dict:
    quien = next(item for item in state["aprobaciones"] if item["decision"] == "n")
    return {"resultado": "RECHAZADO", "respuesta": (
        f"Asunto: RE: {state['correo']['asunto']}\n\nLa desvinculación fue rechazada por "
        f"{quien['aprobador']} ({quien['rol']}). No se ejecutó ningún cambio.")}


def ejecutar(state: Estado, runtime: Runtime[Contexto]) -> dict:
    # Segunda barrera, por si alguien llega aquí sin pasar por aprobar.
    if pendientes(state):
        raise PermissionError("SIN_APROBACION: faltan " + ", ".join(pendientes(state)))
    git, registro = runtime.context.git, []
    operaciones = {
        "transferir_propiedad": lambda a: git.transferir_propiedad(a["repo"], a["usuario"], a["a"]),
        "quitar_acceso": lambda a: git.quitar_acceso(a["repo"], a["usuario"]),
        "revocar_tokens": lambda a: git.revocar_tokens(a["usuario"]),
        "revocar_llaves_ssh": lambda a: git.revocar_llaves_ssh(a["usuario"]),
        "bloquear_cuenta": lambda a: git.bloquear_cuenta(a["usuario"]),
    }
    for accion in state["plan"]["acciones"]:
        if accion["accion"] not in ACCIONES_PERMITIDAS:
            registro.append({**accion, "ok": False, "detalle": "ACCION_NO_PERMITIDA"})
            continue
        try:
            registro.append({**accion, "ok": True, "detalle": operaciones[accion["accion"]](accion)})
        except GitError as exc:
            registro.append({**accion, "ok": False, "detalle": str(exc)})
    return {"ejecucion": registro}


def verificar(state: Estado, runtime: Runtime[Contexto]) -> dict:
    check = verificar_baja(runtime.context.git, state["evaluacion"]["usuario"], state["plan"])
    ok = check["ok"] and all(item["ok"] for item in state["ejecucion"])
    return {"verificacion": check, "resultado": "EJECUTADO" if ok else "VERIFICACION_FALLIDA"}


# -- Enrutamiento: funciones de las aristas condicionales ----------------------------------------
def ruta_tras_clasificar(state: Estado) -> str:
    """Camino después de clasificar. Devuelve el nombre del siguiente nodo: "archivar" o "extraer"."""
    # TODO(caso 2 · elegir camino). ¿Qué categoría del modelo (state["ruta"]["categoria"]) termina
    # sin extraer nada? ¿Por qué las demás (incluso fuera_de_politica) siguen a extraer y validar?
    raise NotImplementedError("Caso 2 · grafo_baja.ruta_tras_clasificar: decide a qué nodo va cada categoría.")


def ruta_tras_validar(state: Estado) -> str:
    """Camino después de validar: "bloquear", "pedir_informacion" o "planificar".

    Lo decide state["evaluacion"]["decision"] (BLOQUEAR | PEDIR_INFORMACION | PLANIFICAR), que
    calcula politica.evaluar en código. El modelo no participa aquí.
    """
    # TODO(caso 2 · elegir camino). Lleva cada decisión de la política a su nodo.
    raise NotImplementedError("Caso 2 · grafo_baja.ruta_tras_validar: lleva cada decisión de la política a su nodo.")


def despues_de_aprobar(state: Estado) -> str:
    """Camino después de cada aprobación: "aprobar" (otra vez), "rechazar" o "ejecutar"."""
    # TODO(caso 2 · elegir camino en el ciclo de aprobación). Usa state["aprobaciones"] y
    # pendientes(state). ¿Basta un "n" de cualquiera para rechazar? ¿Cuándo se puede ejecutar?
    # ¿Cuándo hay que volver a preguntar?
    raise NotImplementedError("Caso 2 · grafo_baja.despues_de_aprobar: decide si se vuelve a preguntar, "
                              "se rechaza o se ejecuta.")


PASOS = {"clasificar": clasificar, "archivar": archivar, "extraer": extraer, "validar": validar,
         "bloquear": bloquear, "pedir_informacion": pedir_informacion, "planificar": planear,
         "aprobar": aprobar, "rechazar": rechazar, "ejecutar": ejecutar, "verificar": verificar}
FINALES = ("archivar", "bloquear", "pedir_informacion", "rechazar", "verificar")


def build_graph(checkpointer=None):
    """Arma y compila el grafo del caso 2 (ver el diagrama en el README y en docs/caso2_correo.pdf).

    Un grafo de LangGraph tiene nodos (pasos: funciones que reciben el estado y devuelven cambios)
    y aristas (flechas: qué paso sigue). Una arista condicional llama a una función que elige el
    camino. El checkpointer guarda el estado después de cada paso; sin él no hay pausa ni
    continuación.

    Entrada: checkpointer opcional (el trigger usa SqliteSaver, un archivo SQLite).
    Salida: el grafo compilado, con state_schema=Estado y context_schema=Contexto.
    Los nombres de los nodos son las claves de PASOS; los finales están en FINALES.
    """
    # TODO(caso 2 · el grafo). Decide los nodos y las flechas:
    #   - Agrega cada nodo de PASOS con su nombre.
    #   - Flechas fijas: ¿dónde empieza? extraer → validar, planificar → aprobar, ejecutar → verificar.
    #   - Flechas condicionales con ruta_tras_clasificar, ruta_tras_validar y despues_de_aprobar
    #     (indica también los destinos posibles de cada una, para que el diagrama salga completo).
    #   - Cada nodo de FINALES termina en END.
    #   - Compila con el checkpointer: sin él, ¿dónde quedaría guardada la pausa de aprobar?
    raise NotImplementedError("Caso 2 · grafo_baja.build_graph: declara los nodos, las flechas (fijas y "
                              "condicionales) y compila con el checkpointer.")
