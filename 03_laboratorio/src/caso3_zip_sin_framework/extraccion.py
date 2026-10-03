"""Paso 3: un "trabajador" por documento, con salida estructurada y un bucle evaluador-optimizador.

Sin framework: el cliente oficial de OpenAI apunta al mismo endpoint compatible (Groq o
LM Studio) y pide JSON Schema estricto. Si las reglas de reglas.py encuentran problemas,
se le devuelven al modelo como retroalimentación y se reintenta, máximo MAX_INTENTOS veces.
"""
from __future__ import annotations

import json
import time

from settings import PROMPTS

from .reglas import TIPOS, evaluar_extraccion

MAX_INTENTOS = 2          # 1 extracción + 1 corrección; después, revisión humana
MAX_CARACTERES = 6_000    # un soporte más largo se recorta antes de enviarlo
MAX_OUTPUT_TOKENS = 600

ESQUEMA = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": list(TIPOS)},
        "codigo_literal": {"type": ["string", "null"]},
        "fecha": {"type": ["string", "null"]},
        "monto_solicitado": {"type": ["integer", "null"]},
        "pagos": {"type": "array", "items": {"type": "integer"}},
        "numero_desembolsos": {"type": ["integer", "null"]},
    },
    "required": ["tipo", "codigo_literal", "fecha", "monto_solicitado", "pagos", "numero_desembolsos"],
    "additionalProperties": False,
}


def leer_prompt() -> str:
    return (PROMPTS / "caso3_extraer.txt").read_text(encoding="utf-8").strip()


def llamar_modelo(client, backend, messages: list[dict], trace=None) -> dict:
    """Una llamada con JSON Schema estricto, tope de salida y cero reintentos del cliente."""
    extra = {"reasoning_effort": backend.reasoning_effort} if backend.reasoning_effort else {}
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=backend.model, messages=messages, temperature=0, max_tokens=MAX_OUTPUT_TOKENS,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "soporte", "strict": True, "schema": ESQUEMA}}, **extra)
    choice = response.choices[0]
    usage = getattr(response, "usage", None)
    if trace is not None:
        trace.emit("model_response", purpose="caso3_extraer", seconds=round(time.perf_counter() - started, 2),
                   finish_reason=choice.finish_reason, content=choice.message.content,
                   tokens={"entrada": getattr(usage, "prompt_tokens", None),
                           "salida": getattr(usage, "completion_tokens", None),
                           "total": getattr(usage, "total_tokens", None)})
    if choice.finish_reason in ("length", "content_filter"):
        raise ValueError(f"Respuesta incompleta del modelo: {choice.finish_reason}.")
    return json.loads(choice.message.content)


def extraer_documento(client, backend, nombre: str, texto: str, trace=None) -> dict:
    """Trabajador de UN documento: el modelo extrae, el evaluador revisa y, si hace falta, se corrige.

    Este ir y venir se llama evaluador-optimizador: alguien produce (el modelo), alguien revisa
    (las reglas) y la crítica vuelve a quien produce. Aquí tiene un límite: MAX_INTENTOS.

    Entrada: client (openai.OpenAI o el doble de las pruebas), backend (model.Backend), nombre
        del soporte, su texto y, si se quiere, una traza (trace.emit(evento, **datos)).
    Salida (dict):
        nombre: str
        extraccion: dict | None      (el último JSON del modelo; None si nunca fue JSON válido)
        verificado: bool             (True si el último intento no tiene problemas)
        problemas: list[str]         (los del último intento)
        intentos: int                (cuántas veces se llamó al modelo; máximo MAX_INTENTOS)
        historial: list[dict]        ({"intento", "extraccion", "problemas"} por intento)

    Ya tienes: leer_prompt(), llamar_modelo(...) (una llamada con JSON Schema estricto; lanza
    ValueError si la respuesta llega cortada) y reglas.evaluar_extraccion(texto, extraccion).
    El documento va entre etiquetas: <documento nombre="...">texto (máx. MAX_CARACTERES)</documento>.
    """
    messages = [{"role": "system", "content": leer_prompt()},
                {"role": "user", "content": f"<documento nombre=\"{nombre}\">\n{texto[:MAX_CARACTERES]}\n</documento>"}]
    intentos = []
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            extraccion = llamar_modelo(client, backend, messages, trace)
        except json.JSONDecodeError:
            extraccion, problemas = None, ["La respuesta no fue un JSON válido."]
        else:
            problemas = evaluar_extraccion(texto, extraccion)
        intentos.append({"intento": intento, "extraccion": extraccion, "problemas": problemas})
        if trace is not None:
            trace.emit("evaluacion", documento=nombre, intento=intento, problemas=problemas)
        if not problemas:
            break
        # Optimizador: la crítica es de las reglas, no de otro modelo. Se pide corregir solo eso.
        messages += [{"role": "assistant", "content": json.dumps(extraccion, ensure_ascii=False)},
                     {"role": "user", "content": "Las validaciones encontraron estos problemas; corrige el JSON "
                                                 "usando solo lo escrito en el documento:\n- " + "\n- ".join(problemas)}]
    final = intentos[-1]
    return {"nombre": nombre, "extraccion": final["extraccion"], "verificado": not final["problemas"],
            "problemas": final["problemas"], "intentos": len(intentos), "historial": intentos}
