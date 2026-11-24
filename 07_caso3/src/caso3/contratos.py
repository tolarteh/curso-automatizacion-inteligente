"""Contratos compartidos del expediente sintético, sin llamadas a modelos."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Documento(Contract):
    id: str
    tipo: Literal["solicitud", "cotizacion", "factura", "certificado", "otro"]
    ruta: str
    texto: str


class Clasificacion(Contract):
    documentos: list[Documento]
    faltantes: list[str]


class Item(Contract):
    descripcion: str
    cantidad: int = Field(gt=0)
    valor_unitario: Decimal = Field(ge=0)


class Extraccion(Contract):
    doc_id: str
    nit: str
    monto_total: Decimal = Field(ge=0)
    iva_incluido: bool | None
    fecha: date
    items: list[Item]
    es_ganadora: bool

    @field_validator("monto_total", mode="before")
    @classmethod
    def reject_float(cls, value):
        if isinstance(value, float):
            raise ValueError("El monto debe llegar como cadena decimal, no float.")
        return value


class ReglaCitada(Contract):
    fuente: str
    version: str
    vigente_desde: date
    texto: str


class Hallazgo(Contract):
    codigo: str
    severidad: Literal["bloqueante", "observacion"]
    detalle: str
    regla: ReglaCitada | None = None
    devolver_a: Literal["extractor", "verificador"] | None = None


class Dictamen(Contract):
    decision: Literal["aprobar", "devolver", "escalar"]
    hallazgos: list[Hallazgo]
    reglas: list[ReglaCitada]
    vueltas: int = Field(ge=0, le=2)
    requiere_firma: Literal[True] = True


class Paso(Contract):
    agente: str
    entrada_resumen: str
    salida_resumen: str
    ms: float = Field(ge=0)


class Traza(Contract):
    expediente_id: str
    pasos: list[Paso]
    vueltas: int = Field(ge=0, le=2)


class Extracciones(Contract):
    extracciones: list[Extraccion]


class Reglas(Contract):
    reglas: list[ReglaCitada]


class Hallazgos(Contract):
    hallazgos: list[Hallazgo]
