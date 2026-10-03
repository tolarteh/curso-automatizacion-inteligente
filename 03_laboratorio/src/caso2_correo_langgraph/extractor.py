"""Los dos pasos con modelo del caso 2: clasificar (elegir el camino) y extraer datos.

Ambos usan salida estructurada (JSON Schema estricto): el modelo llena campos con tipos
y valores permitidos, y el código valida después (politica.py). El correo va delimitado
y el prompt lo trata como dato, pero la defensa real está en el código.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from settings import PROMPTS

from .politica import SOLICITUDES

Categoria = Literal["baja", "ambiguo", "fuera_de_politica", "irrelevante"]
Solicitud = Literal[SOLICITUDES]  # type: ignore[valid-type]


class Ruta(BaseModel):
    categoria: Categoria
    motivo: str = Field(description="Una frase corta")


class Datos(BaseModel):
    radicado: str | None
    nombre: str | None
    usuario: str | None
    fecha_efectiva: str | None = Field(description="AAAA-MM-DD")
    repos_mencionados: list[str]
    solicitudes: list[Solicitud]


def leer_prompt(nombre: str) -> str:
    return (PROMPTS / nombre).read_text(encoding="utf-8").strip()


def delimitar(correo: dict) -> str:
    return (f"<correo>\nDe: {correo['nombre_remitente']} <{correo['remitente']}>\n"
            f"Asunto: {correo['asunto']}\n\n{correo['cuerpo']}\n</correo>")


class LlmExtractor:
    """Envuelve un chat model de LangChain (ChatOpenAI hacia Groq o LM Studio)."""

    def __init__(self, llm, callbacks=()):
        self.clasificador = llm.with_structured_output(Ruta, method="json_schema", strict=True)
        self.extractor = llm.with_structured_output(Datos, method="json_schema", strict=True)
        self.config = {"callbacks": list(callbacks)}

    def clasificar(self, correo: dict) -> dict:
        messages = [("system", leer_prompt("caso2_clasificar.txt")), ("human", delimitar(correo))]
        return _a_dict(self.clasificador.invoke(messages, config=self.config))

    def extraer(self, correo: dict) -> dict:
        messages = [("system", leer_prompt("caso2_extraer.txt")), ("human", delimitar(correo))]
        return _a_dict(self.extractor.invoke(messages, config=self.config))


def _a_dict(result) -> dict:
    if result is None:
        raise ValueError("El modelo no devolvió un JSON válido para el esquema.")
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)
