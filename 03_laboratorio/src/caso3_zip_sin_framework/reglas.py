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
    # TODO(caso 3 · evaluador). Decide qué hace creíble una extracción. Revisa al menos:
    #   1. Tipo y código escrito. Si el documento dice «Formato: XXX-XXX-NN» (regex FORMATO),
    #      ¿qué tipo le corresponde? Cuidado con códigos parecidos que no están en CATALOGO,
    #      como FAC-AMZ-09. ¿Y si el modelo dice DEM-AMZ-xx pero el código no está escrito?
    #   2. Campos obligatorios de cada tipo (REQUERIDOS).
    #   3. Montos inventados: ¿cada monto (monto_solicitado y pagos) aparece escrito en el texto?
    #      numeros(texto) ya entiende «48.500.000» y «48500000».
    #   4. Fechas: ¿tienen formato AAAA-MM-DD y aparecen escritas en el documento?
    raise NotImplementedError("Caso 3 · reglas.evaluar_extraccion: escribe las revisiones del evaluador "
                              "(tipo y código, campos obligatorios, montos y fechas que sí estén en el texto).")


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
    # TODO(caso 3 · reglas de negocio). Con las constantes de arriba y el procedimiento PR-FIN-012
    # (02_rag/data/corpus/PR-FIN-012_amortizaciones.md), decide cuándo se DEVUELVE, cuándo va
    # a EN_REVISION y cuándo queda LISTA_PARA_APROBACION:
    #   - Soportes obligatorios (OBLIGATORIOS) y DEM-AMZ-07 si hay más de un desembolso.
    #   - Vigencia de la certificación bancaria: máximo VIGENCIA_CERTIFICACION días antes de la radicación.
    #   - Cruce de montos: lo solicitado contra la suma de los pagos, con tolerancia(...).
    #   - Un soporte que llegó pero quedó NO verificado: ¿es un faltante (devolver) o una duda
    #     que debe mirar una persona (revisión)?
    #   - Si hay motivos para devolver y para revisar a la vez, ¿cuál gana?
    raise NotImplementedError("Caso 3 · reglas.decidir: escribe las reglas de PR-FIN-012 que llevan a "
                              "LISTA_PARA_APROBACION, EN_REVISION o DEVOLVER.")
