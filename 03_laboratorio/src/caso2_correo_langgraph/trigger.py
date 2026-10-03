"""El disparador: consume una MailSource y lleva cada correo nuevo por el grafo.

Un correo = un hilo (thread_id). El checkpointer SQLite guarda dónde quedó cada hilo:
- terminado: no se reprocesa aunque la fuente lo vuelva a entregar;
- detenido en aprobar (interrupt): queda pendiente hasta que una persona decida;
- interrumpido por un error (por ejemplo, un 429): se reanuda desde el último paso guardado.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .grafo_baja import RECURSION_LIMIT, Contexto, pendientes
from .politica import validar_aprobacion


def abrir_checkpointer(path: Path) -> SqliteSaver:
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def thread_de(correo_id: str) -> str:
    """Un hilo por correo. Los ids de Graph son largos y comparten prefijo: se resumen con un hash."""
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", correo_id):
        return f"correo-{correo_id}"
    return "correo-" + hashlib.sha256(correo_id.encode("utf-8")).hexdigest()[:20]


def _config(thread_id: str, callbacks=()) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT,
            "callbacks": list(callbacks)}


def _correr(app, entrada, thread_id: str, contexto: Contexto, on_node=None, callbacks=()) -> dict:
    for chunk in app.stream(entrada, _config(thread_id, callbacks), context=contexto,
                            stream_mode="updates"):
        for node, update in chunk.items():
            if on_node and node != "__interrupt__":
                on_node(node, update)
    return resumen(app, thread_id)


def resumen(app, thread_id: str) -> dict:
    snapshot = app.get_state({"configurable": {"thread_id": thread_id}})
    values = snapshot.values or {}
    interrupcion = snapshot.interrupts[0].value if snapshot.interrupts else None
    if interrupcion is not None:
        estado = "PENDIENTE_APROBACION"
    elif snapshot.next:
        estado = "INCOMPLETO"
    else:
        estado = values.get("resultado", "SIN_INICIAR" if not values else "INCOMPLETO")
    return {"thread_id": thread_id, "estado": estado, "asunto": (values.get("correo") or {}).get("asunto"),
            "ruta": values.get("ruta"), "evaluacion": values.get("evaluacion"), "plan": values.get("plan"),
            "aprobaciones": values.get("aprobaciones", []), "ejecucion": values.get("ejecucion"),
            "verificacion": values.get("verificacion"), "respuesta": values.get("respuesta"),
            "interrupcion": interrupcion}


def procesar_correo(app, correo, contexto: Contexto, *, on_node=None, callbacks=()) -> dict:
    thread_id = thread_de(correo.id)
    actual = resumen(app, thread_id)
    if actual["estado"] == "INCOMPLETO":       # quedó a medias por un error: se reanuda
        return _correr(app, None, thread_id, contexto, on_node, callbacks)
    if actual["estado"] != "SIN_INICIAR":      # terminado o pendiente: no se repite
        return {**actual, "repetido": True}
    return _correr(app, {"correo": correo.to_dict()}, thread_id, contexto, on_node, callbacks)


def listar_hilos(checkpointer) -> list[str]:
    hilos = []
    for item in checkpointer.list(None):
        thread_id = item.config["configurable"]["thread_id"]
        if thread_id not in hilos:
            hilos.append(thread_id)
    return sorted(hilos)


def listar_pendientes(app, checkpointer) -> list[dict]:
    return [r for r in (resumen(app, t) for t in listar_hilos(checkpointer))
            if r["estado"] == "PENDIENTE_APROBACION"]


def decidir(app, thread_id: str, decision: str, contexto: Contexto, *, rol=None, aprobador="",
            comentario="", on_node=None) -> dict:
    """Reanuda un hilo detenido en aprobar con la decisión de una persona."""
    actual = resumen(app, thread_id)
    if actual["estado"] != "PENDIENTE_APROBACION":
        raise ValueError(f"El hilo {thread_id} no está pendiente de aprobación ({actual['estado']}).")
    faltan = actual["interrupcion"]["pendientes"]
    respuesta = validar_aprobacion({"decision": decision, "rol": rol, "aprobador": aprobador,
                                    "comentario": comentario}, faltan)
    return _correr(app, Command(resume=respuesta), thread_id, contexto, on_node)


def guardar_borrador(carpeta: Path, resultado: dict) -> Path | None:
    """Los borradores de respuesta se guardan en outputs; el sistema no envía correos."""
    if not resultado.get("respuesta"):
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    path = carpeta / f"{resultado['thread_id']}.txt"
    path.write_text(resultado["respuesta"] + "\n", encoding="utf-8")
    return path


def mostrar(resultado: dict) -> str:
    lineas = [f"{resultado['thread_id']}: {resultado['estado']}"
              + (" (ya procesado)" if resultado.get("repetido") else "")]
    if resultado.get("ruta"):
        lineas.append(f"  ruta del modelo: {resultado['ruta']['categoria']} — {resultado['ruta']['motivo']}")
    evaluacion = resultado.get("evaluacion") or {}
    for item in evaluacion.get("hallazgos", []):
        lineas.append(f"  bloqueo en código: {item}")
    for item in evaluacion.get("faltantes", []):
        lineas.append(f"  falta: {item}")
    if resultado.get("interrupcion"):
        pausa = resultado["interrupcion"]
        lineas.append(f"  baja propuesta: {pausa['nombre']} ({pausa['usuario']}), radicado {pausa['radicado']}, "
                      f"jefe inmediato {pausa['jefe_inmediato']} (según Talento Humano, no según el correo)")
        mencionados = ", ".join(pausa.get("repos_mencionados") or []) or "ninguno"
        lineas.append(f"  repos en el correo: {mencionados}; el plan usa el inventario del proveedor:")
        for accion in pausa["plan"]["acciones"]:
            lineas.append("    · " + json.dumps(accion, ensure_ascii=False))
        if pausa["plan"]["custodia_especial"]:
            lineas.append("  custodia especial: " + ", ".join(pausa["plan"]["custodia_especial"])
                          + " → plazo 1 día hábil; seguridad revisa secretos y guarda copia antes de transferir")
        for item in pausa.get("aprobaciones", []):
            lineas.append(f"  aprobó {item['rol']}: {item['aprobador']}")
        lineas.append(f"  aprobaciones pendientes: {', '.join(pausa['pendientes'])}")
    for item in resultado.get("ejecucion") or []:
        lineas.append(f"  {'ok ' if item['ok'] else 'ERR'} {item['detalle']}")
    if resultado.get("verificacion"):
        check = resultado["verificacion"]
        lineas.append("  verificación en el proveedor: " + ("OK" if check["ok"] else "; ".join(check["problemas"])))
    return "\n".join(lineas)
