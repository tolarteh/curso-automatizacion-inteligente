"""Reglas en Python: evaluador de cada extracción y reglas de negocio de PR-FIN-012.

El modelo lee y llena campos; aquí se decide si lo que llenó es creíble (está en el
documento) y qué pasa con la solicitud. Ninguna regla depende del prompt.
"""
from __future__ import annotations

import re
from datetime import date

# Formatos del catálogo CT-FIN-003 que este flujo reconoce. Un código parecido (FAC-AMZ-09)
# no es DEM-AMZ-09: un código fuera del catálogo se trata como OTRO.
TIPOS = ("DEM-AMZ-03", "DEM-AMZ-05", "DEM-AMZ-07", "FACTURA", "COMPROBANTE_PAGO", "OTRO")
CATALOGO = frozenset(f"DEM-AMZ-{n:02d}" for n in range(1, 10))
OBLIGATORIOS = ("DEM-AMZ-03", "DEM-AMZ-05", "FACTURA")
VIGENCIA_CERTIFICACION = 30          # días entre expedición y radicación
TOLERANCIA_PORCENTAJE = 0.005        # 0,5 % del monto solicitado...
TOLERANCIA_MAXIMA = 200_000          # ...o 200.000 pesos: se aplica el menor
PLAZO_DEVOLUCION = 3                 # días hábiles para devolver una solicitud incompleta
# Decisiones que el sistema puede SUGERIR. Aprobar o pagar es de una persona.
DECISIONES = ("LISTA_PARA_APROBACION", "EN_REVISION", "DEVOLVER")

FORMATO = re.compile(r"Formato:\s*([A-Z]{3}-[A-Z]{3}-\d{2})")
REQUERIDOS = {
    "DEM-AMZ-03": ("monto_solicitado", "fecha", "numero_desembolsos"),
    "DEM-AMZ-05": ("fecha",),
    "DEM-AMZ-07": ("pagos",),
    "COMPROBANTE_PAGO": ("pagos",),
}


def numeros(texto: str) -> set[int]:
    """Todos los montos escritos en el texto: 48.500.000 (miles con punto) o 48500000 (CSV)."""
    found = {int(run) for run in re.findall(r"\d+", texto)}
    found |= {int(group.replace(".", "")) for group in re.findall(r"\d{1,3}(?:\.\d{3})+", texto)}
    return found


def evaluar_extraccion(texto: str, extraccion: dict) -> list[str]:
    """Evaluador: revisa lo que el modelo sacó de UN documento, comparándolo con el texto.

    Entrada:
        texto: el texto completo del soporte (lo mismo que leyó el modelo).
        extraccion: el JSON del modelo, con las claves de extraccion.ESQUEMA
            (tipo, codigo_literal, fecha, monto_solicitado, pagos, numero_desembolsos).
    Salida:
        Una lista de problemas, en frases cortas. Lista vacía = la extracción es creíble.
        Cada problema nombra el valor que falla (por ejemplo «48000000» o «2026-09-21»),
        porque ese texto se le devuelve al modelo para que corrija.

    El evaluador es código, no otro modelo. Nada de lo que decidas aquí depende del prompt.
    """
    problemas = []
    tipo = extraccion.get("tipo")
    declarado = FORMATO.search(texto)
    if declarado:
        codigo = declarado.group(1)
        esperado = codigo if codigo in CATALOGO and codigo in TIPOS else "OTRO"
        if tipo != esperado:
            problemas.append(f"El documento declara «Formato: {codigo}»; el tipo debe ser {esperado}, no {tipo}.")
    elif tipo and tipo.startswith("DEM-AMZ"):
        problemas.append(f"El tipo {tipo} exige que el código aparezca escrito en el documento.")
    for campo in REQUERIDOS.get(tipo, ()):
        if extraccion.get(campo) in (None, [], ""):
            problemas.append(f"Falta {campo} para un documento {tipo}.")
    presentes = numeros(texto)
    montos = [extraccion.get("monto_solicitado")] + list(extraccion.get("pagos") or [])
    for monto in montos:
        if monto is not None and monto not in presentes:
            problemas.append(f"El monto {monto} no aparece escrito en el documento.")
    fecha = extraccion.get("fecha")
    if fecha is not None:
        try:
            date.fromisoformat(fecha)
        except (TypeError, ValueError):
            problemas.append(f"La fecha {fecha} no tiene formato AAAA-MM-DD.")
        else:
            if fecha not in texto:
                problemas.append(f"La fecha {fecha} no aparece escrita en el documento.")
    return problemas


def pesos(valor: int) -> str:
    """48500000 → 48.500.000 (miles con punto, como en los soportes)."""
    return f"{valor:,}".replace(",", ".")


def tolerancia(solicitado: int) -> int:
    return min(round(solicitado * TOLERANCIA_PORCENTAJE), TOLERANCIA_MAXIMA)


def decidir(documentos: list[dict]) -> dict:
    """Reglas de negocio de PR-FIN-012 sobre los soportes ya leídos. El sistema sugiere, no aprueba.

    Entrada: un dict por soporte, como los arma pipeline.procesar_zip:
        {"nombre": str, "texto": str, "extraccion": dict | None, "verificado": bool, ...}
        Solo cuentan como prueba los soportes con verificado=True.
    Salida (dict):
        decision: una de DECISIONES ("LISTA_PARA_APROBACION", "EN_REVISION", "DEVOLVER").
        motivos: list[str] con el porqué (vacía si queda LISTA_PARA_APROBACION).
            Si la certificación está vencida, el motivo dice cuántos días tiene («57 días»).
        observaciones: list[str] con hallazgos que no cambian la decisión. Por ejemplo, un código
            de formato que no existe en CATALOGO (el texto debe nombrar ese código).
        cruce: None o {"monto_solicitado", "suma_pagada", "diferencia", "tolerancia",
            "dentro_de_tolerancia"} (pesos enteros y un bool).
        faltantes: list[str] con los tipos obligatorios que no llegaron (p. ej. ["FACTURA", "DEM-AMZ-07"]).
        responsable: un texto que deje claro que aprobar le toca a una persona.
    """
    verificados = [d for d in documentos if d["verificado"]]
    por_tipo: dict[str, list[dict]] = {}
    for doc in verificados:
        por_tipo.setdefault(doc["extraccion"]["tipo"], []).append(doc["extraccion"])
    motivos_devolver, motivos_revision, observaciones = [], [], []

    no_verificados = [d["nombre"] for d in documentos if not d["verificado"]]
    # Un soporte que existe pero no se pudo verificar va a revisión humana, no se da por faltante.
    tipos_dudosos = {(d["extraccion"] or {}).get("tipo") for d in documentos if not d["verificado"]}
    if no_verificados:
        motivos_revision.append("Extracción no verificada tras los reintentos: " + ", ".join(no_verificados))
    for doc in verificados:
        declarado = FORMATO.search(doc["texto"])
        if declarado and declarado.group(1) not in CATALOGO:
            observaciones.append(f"{doc['nombre']}: el formato {declarado.group(1)} no existe en el catálogo CT-FIN-003.")

    solicitud = (por_tipo.get("DEM-AMZ-03") or [None])[0]
    desembolsos = (solicitud or {}).get("numero_desembolsos") or 0
    requeridos = list(OBLIGATORIOS) + (["DEM-AMZ-07"] if desembolsos > 1 else [])
    faltantes = [tipo for tipo in requeridos if tipo not in por_tipo and tipo not in tipos_dudosos]
    if faltantes:
        motivos_devolver.append("Faltan soportes obligatorios: " + ", ".join(faltantes))

    certificacion = (por_tipo.get("DEM-AMZ-05") or [None])[0]
    if solicitud and certificacion:
        dias = (date.fromisoformat(solicitud["fecha"]) - date.fromisoformat(certificacion["fecha"])).days
        if not 0 <= dias <= VIGENCIA_CERTIFICACION:
            motivos_devolver.append(f"Certificación bancaria con {dias} días a la radicación "
                                    f"(máximo {VIGENCIA_CERTIFICACION}).")

    cruce = None
    pagos = [p for comprobante in por_tipo.get("COMPROBANTE_PAGO", []) for p in comprobante["pagos"]]
    if solicitud and pagos:
        solicitado, pagado = solicitud["monto_solicitado"], sum(pagos)
        limite = tolerancia(solicitado)
        cruce = {"monto_solicitado": solicitado, "suma_pagada": pagado, "diferencia": abs(solicitado - pagado),
                 "tolerancia": limite, "dentro_de_tolerancia": abs(solicitado - pagado) <= limite}
        if not cruce["dentro_de_tolerancia"]:
            motivos_revision.append(f"Diferencia de {pesos(cruce['diferencia'])} supera la tolerancia de "
                                    f"{pesos(limite)} (0,5 % o 200.000, el menor).")
    elif solicitud and "COMPROBANTE_PAGO" in tipos_dudosos:
        motivos_revision.append("El cruce de montos requiere revisión manual de los comprobantes.")
    elif solicitud:
        motivos_devolver.append("No hay comprobantes de pago para el cruce de montos.")

    if motivos_devolver:
        decision = "DEVOLVER"
        motivos_devolver.append(f"Devolver al solicitante dentro de {PLAZO_DEVOLUCION} días hábiles.")
    elif motivos_revision:
        decision = "EN_REVISION"
        motivos_revision.append("Grupo de Control Financiero: 5 días hábiles. No se puede aprobar en este estado.")
    else:
        decision = "LISTA_PARA_APROBACION"
    return {"decision": decision, "motivos": motivos_devolver + motivos_revision,
            "observaciones": observaciones, "cruce": cruce, "faltantes": faltantes,
            "responsable": "pendiente: la aprobación es de una persona, no del sistema"}
