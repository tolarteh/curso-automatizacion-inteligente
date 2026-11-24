"""Controles en código del procedimiento PR-TIC-004. El modelo propone; esto decide.

Ninguna de estas reglas depende del prompt: si el modelo clasifica mal o extrae de más,
el correo igual se bloquea o se devuelve. El modelo solo puede volver la decisión más
conservadora (por ejemplo, marcar "ambiguo"), nunca menos.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

# Solo Talento Humano dispara una desvinculación (PR-TIC-004, sección 2).
REMITENTES_AUTORIZADOS = frozenset({"talento.humano@aurora.example"})
# Lo único que el sistema puede ejecutar. El proveedor Git tampoco ofrece otra cosa.
ACCIONES_PERMITIDAS = ("transferir_propiedad", "quitar_acceso", "revocar_tokens",
                       "revocar_llaves_ssh", "bloquear_cuenta")
# Lo que el modelo puede detectar que el correo pide y que nunca se ejecuta.
SOLICITUDES_PROHIBIDAS = frozenset({"borrar_cuenta_definitivamente", "borrar_repositorio",
                                    "otorgar_admin", "agregar_acceso"})
SOLICITUDES = ("desvincular_o_bloquear", "revocar_accesos", "transferir_propiedad",
               "borrar_cuenta_definitivamente", "borrar_repositorio", "otorgar_admin", "agregar_acceso",
               "otra")
# Dos aprobaciones registradas antes de ejecutar (PR-TIC-004, sección 4).
APROBACIONES_REQUERIDAS = ("jefe_inmediato", "seguridad")
# Lo que puede decidir evaluar(); cada decisión lleva a un nodo distinto del grafo.
DECISIONES_POLITICA = ("BLOQUEAR", "PEDIR_INFORMACION", "PLANIFICAR")
# Repositorios con custodia especial (AC-SEG-2026-08): plazo de 1 día hábil y revisión de secretos.
REPOS_CUSTODIA = frozenset({"sim-procesos-core", "telemetria-sensores", "archivo-enlaces"})

RADICADO = re.compile(r"TH-\d{4}-\d{4}")
USUARIO = re.compile(r"[a-z][a-z0-9.-]{1,30}")
# Detector en el texto del correo, independiente del modelo (se compara sin tildes).
PATRONES_PROHIBIDOS = (
    ("borrar o eliminar repositorios, cuentas o historial",
     re.compile(r"\b(borr|elimin|suprim|destru)\w*\b(?:\W+\w+){0,5}?\W+"
                r"(repositorio|repos?|cuenta|historial|rama)s?\b")),
    ("otorgar permisos de administrador o propietario",
     re.compile(r"\b(admin|administrador(?:es)?|owner)\b")),
)


def plano(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def patrones_prohibidos(texto: str) -> list[str]:
    plain = plano(texto)
    return [nombre for nombre, patron in PATRONES_PROHIBIDOS if patron.search(plain)]


def fecha_valida(valor) -> bool:
    try:
        date.fromisoformat(valor)
        return True
    except (TypeError, ValueError):
        return False


def evaluar(correo: dict, ruta: dict, datos: dict, talento: dict, git, remitentes=REMITENTES_AUTORIZADOS) -> dict:
    """Decide BLOQUEAR, PEDIR_INFORMACION o PLANIFICAR. El modelo propone; el código decide.

    Entrada:
        correo: el correo como dict (remitente, asunto, cuerpo...).
        ruta: {"categoria", "motivo"} que dio el clasificador (el modelo).
        datos: lo que extrajo el modelo (radicado, nombre, usuario, fecha_efectiva,
            repos_mencionados, solicitudes). Puede venir mal o inventado.
        talento: radicados del sistema simulado de Talento Humano ({radicado: {usuario, nombre,
            fecha_efectiva, jefe_inmediato}}).
        git: el proveedor Git (solo para leer: git.usuario(login) → {"estado": ...} o None).
        remitentes: direcciones que pueden pedir una baja.
    Salida (dict):
        decision: una de DECISIONES_POLITICA.
        hallazgos: list[str] con los motivos de bloqueo. Cada uno empieza con su código:
            REMITENTE_NO_AUTORIZADO, SOLICITUD_FUERA_DE_POLITICA, TEXTO_FUERA_DE_POLITICA o
            CLASIFICADO_FUERA_DE_POLITICA. Si aplica, el del remitente va primero.
        faltantes: list[str] con lo que hay que pedirle al remitente. Nombra el dato
            («radicado», «usuario», «fecha efectiva»). Si el radicado es de otra persona, dilo
            con esas palabras: «otra persona».
        Solo si decision == "PLANIFICAR": radicado (str), usuario (str) y registro (el dict de
            talento para ese radicado; planificar usa registro["jefe_inmediato"]).
    """
    texto = f"{correo.get('asunto', '')}\n{correo.get('cuerpo', '')}"
    bloqueos, faltantes = [], []

    if correo.get("remitente") not in remitentes:
        bloqueos.append(f"REMITENTE_NO_AUTORIZADO: {correo.get('remitente') or '(vacío)'}")
    pedidas = sorted(set(datos.get("solicitudes") or []) & SOLICITUDES_PROHIBIDAS)
    if pedidas:
        bloqueos.append("SOLICITUD_FUERA_DE_POLITICA: " + ", ".join(pedidas))
    for nombre in patrones_prohibidos(texto):
        bloqueos.append(f"TEXTO_FUERA_DE_POLITICA: {nombre}")
    if ruta.get("categoria") == "fuera_de_politica":
        bloqueos.append("CLASIFICADO_FUERA_DE_POLITICA por el modelo")
    if bloqueos:
        return {"decision": "BLOQUEAR", "hallazgos": bloqueos, "faltantes": []}

    # El modelo extrae; el código comprueba que lo extraído esté en el correo y en los sistemas.
    radicado = (datos.get("radicado") or "").strip().upper()
    usuario = (datos.get("usuario") or "").strip().lower()
    if not RADICADO.fullmatch(radicado) or radicado not in texto.upper():
        faltantes.append("radicado de Talento Humano (TH-AAAA-NNNN) escrito en el correo")
    if not USUARIO.fullmatch(usuario) or not re.search(rf"\b{re.escape(usuario)}\b", texto.lower()):
        faltantes.append("usuario de red escrito en el correo")
    if not fecha_valida(datos.get("fecha_efectiva")):
        faltantes.append("fecha efectiva")
    if not faltantes:
        registro = talento.get(radicado)
        if registro is None:
            faltantes.append(f"un radicado vigente: {radicado} no existe en Talento Humano")
        elif registro["usuario"] != usuario:
            faltantes.append(f"confirmar el usuario: el radicado {radicado} corresponde a otra persona")
        elif registro["fecha_efectiva"] != datos.get("fecha_efectiva"):
            faltantes.append("confirmar la fecha efectiva: no coincide con Talento Humano")
        cuenta = git.usuario(usuario)
        if cuenta is None:
            faltantes.append(f"confirmar el usuario: {usuario} no tiene cuenta en Git")
        elif cuenta["estado"] != "activa":
            faltantes.append(f"revisar el caso: la cuenta {usuario} ya está {cuenta['estado']}")
    if ruta.get("categoria") == "ambiguo" and not faltantes:
        faltantes.append("confirmación: el modelo marcó el correo como ambiguo")
    if faltantes:
        return {"decision": "PEDIR_INFORMACION", "hallazgos": [], "faltantes": faltantes}
    return {"decision": "PLANIFICAR", "hallazgos": [], "faltantes": [],
            "radicado": radicado, "usuario": usuario, "registro": talento[radicado]}


def planificar(usuario: str, jefe: str, git) -> dict:
    """El plan sale del inventario del proveedor y del procedimiento, no del texto del correo."""
    acciones, custodia = [], []
    for repo in git.repos_de(usuario):
        if repo["nombre"] in REPOS_CUSTODIA:
            custodia.append(repo["nombre"])
        if repo["rol"] == "propietario" and repo["propietarios"] == [usuario]:
            acciones.append({"accion": "transferir_propiedad", "repo": repo["nombre"], "a": jefe})
        else:
            acciones.append({"accion": "quitar_acceso", "repo": repo["nombre"]})
    acciones += [{"accion": "revocar_tokens"}, {"accion": "revocar_llaves_ssh"},
                 {"accion": "bloquear_cuenta"}]
    for item in acciones:
        item["usuario"] = usuario
    return {"acciones": acciones, "custodia_especial": sorted(custodia),
            "plazo_dias_habiles": 1 if custodia else 2,
            "nota": "Sin eliminación: la cuenta solo se puede eliminar 90 días después del bloqueo."}


def validar_aprobacion(respuesta, pendientes: list[str]) -> dict:
    """La respuesta humana también se valida: s/n explícito, rol pendiente y nombre."""
    if not isinstance(respuesta, dict):
        raise ValueError("APROBACION_INVALIDA: se espera un diccionario.")
    decision = str(respuesta.get("decision", "")).strip().lower()
    if decision not in ("s", "n"):
        raise ValueError("APROBACION_INVALIDA: la decisión debe ser s o n.")
    rol = respuesta.get("rol") or (pendientes[0] if pendientes else None)
    if rol not in pendientes:
        raise ValueError(f"APROBACION_INVALIDA: el rol {rol} no está pendiente ({', '.join(pendientes)}).")
    aprobador = str(respuesta.get("aprobador", "")).strip()
    if not aprobador:
        raise ValueError("APROBACION_INVALIDA: falta el nombre de quien decide.")
    return {"decision": decision, "rol": rol, "aprobador": aprobador[:80],
            "comentario": str(respuesta.get("comentario", ""))[:200]}
