"""Dobles exclusivos de pruebas, nunca importados por las lecciones."""
from copy import deepcopy


def datos(radicado=None, nombre=None, usuario=None, fecha=None, repos=(), solicitudes=("desvincular_o_bloquear",)):
    return {"radicado": radicado, "nombre": nombre, "usuario": usuario, "fecha_efectiva": fecha,
            "repos_mencionados": list(repos), "solicitudes": list(solicitudes)}


# Lo que respondería un modelo razonable para cada correo del buzón simulado.
GUION_CASO2 = {
    "01_baja_clara": ({"categoria": "baja", "motivo": "datos completos"},
                      datos("TH-2026-0412", "Laura Gómez Ríos", "lgomez", "2026-10-09",
                            ["analitica-proyectos", "portal-convocatorias"])),
    "02_baja_ambigua": ({"categoria": "ambiguo", "motivo": "faltan datos"}, datos(nombre="Carlos")),
    # El modelo se equivoca a propósito: dice "baja" y no detecta lo prohibido. El código igual bloquea.
    "03_fuera_de_politica": ({"categoria": "baja", "motivo": "parece una baja"},
                             datos("TH-2026-0398", "Martín Ruiz Peña", "mruiz", "2026-10-07")),
    "04_irrelevante": ({"categoria": "irrelevante", "motivo": "boletín"}, None),
    "05_baja_custodia": ({"categoria": "baja", "motivo": "datos completos"},
                         datos("TH-2026-0420", "Pedro Vargas León", "pvargas", "2026-10-15",
                               ["telemetria-sensores", "sim-procesos-core"])),
    # Inyección: el modelo "obedece" y lo clasifica como baja. El remitente lo bloquea en código.
    "06_proveedor_inyeccion": ({"categoria": "baja", "motivo": "orden aprobada"},
                               datos("TH-2026-9999", None, "dcastano", None)),
}


class FakeExtractor:
    """Clasificador y extractor guionados por id de correo. Registra las llamadas."""

    def __init__(self, guion=None, fallar_primero=None):
        self.guion = deepcopy(guion or GUION_CASO2)
        self.llamadas = []
        self.fallar_primero = fallar_primero

    def _id(self, correo):
        return correo["id"]

    def clasificar(self, correo):
        self.llamadas.append(("clasificar", correo["id"]))
        return deepcopy(self.guion[self._id(correo)][0])

    def extraer(self, correo):
        self.llamadas.append(("extraer", correo["id"]))
        if self.fallar_primero:
            error, self.fallar_primero = self.fallar_primero, None
            raise error
        return deepcopy(self.guion[self._id(correo)][1])


class StructuredFake:
    """Sustituye a un chat model con with_structured_output; devuelve objetos guionados."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.esquemas, self.mensajes = [], []

    def with_structured_output(self, schema, **kwargs):
        self.esquemas.append((schema, kwargs))
        fake = self

        class Runnable:
            def invoke(self, messages, config=None):
                fake.mensajes.append(messages)
                return schema(**fake.respuestas.pop(0))
        return Runnable()


# ----------------------------------------------------------------------------------------------
# Caso 3: cliente OpenAI guionado (chat.completions.create) y extracciones correctas por soporte.
import json as _json
import re as _re
from types import SimpleNamespace


def soporte(tipo, codigo=None, fecha=None, monto=None, pagos=(), desembolsos=None):
    return {"tipo": tipo, "codigo_literal": codigo, "fecha": fecha, "monto_solicitado": monto,
            "pagos": list(pagos), "numero_desembolsos": desembolsos}


EXTRACCIONES_CASO3 = {
    "AMZ-2026-0142_completa": {
        "01_solicitud.txt": soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-22", 48500000, desembolsos=2),
        "02_certificacion_bancaria.txt": soporte("DEM-AMZ-05", "DEM-AMZ-05", "2026-09-10"),
        "03_conciliacion.txt": soporte("DEM-AMZ-07", "DEM-AMZ-07", None, pagos=(24000000, 24420000)),
        "04_factura_FE-3381.txt": soporte("FACTURA", None, "2026-09-05"),
        "05_comprobantes_pago.csv": soporte("COMPROBANTE_PAGO", pagos=(24000000, 24420000)),
    },
    "AMZ-2026-0157_diferencia": {
        "01_solicitud.txt": soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-18", 36200000, desembolsos=1),
        "02_certificacion_bancaria.txt": soporte("DEM-AMZ-05", "DEM-AMZ-05", "2026-09-01"),
        "03_factura_HM-0912.txt": soporte("FACTURA", None, "2026-08-28"),
        "04_comprobante_pago.csv": soporte("COMPROBANTE_PAGO", pagos=(36010000,)),
    },
    "AMZ-2026-0163_incompleta": {
        "01_solicitud.txt": soporte("DEM-AMZ-03", "DEM-AMZ-03", "2026-09-25", 12750000, desembolsos=2),
        "02_certificacion_bancaria.txt": soporte("DEM-AMZ-05", "DEM-AMZ-05", "2026-07-30"),
        "03_anexo_FAC-AMZ-09.txt": soporte("OTRO", "FAC-AMZ-09", None),
        "04_comprobantes_pago.csv": soporte("COMPROBANTE_PAGO", pagos=(6375000, 6375000)),
    },
}


class FakeOpenAI:
    """Cliente con la forma de openai.OpenAI. Responde por nombre de documento o en orden."""

    def __init__(self, por_documento=None, en_orden=None, finish_reason="stop"):
        self.por_documento = por_documento or {}
        self.en_orden = list(en_orden or [])
        self.finish_reason = finish_reason
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.en_orden:
            content = self.en_orden.pop(0)
        else:
            nombre = _re.search(r'nombre="([^"]+)"', kwargs["messages"][1]["content"]).group(1)
            content = self.por_documento[nombre]
        text = content if isinstance(content, str) else _json.dumps(content)
        usage = SimpleNamespace(prompt_tokens=300, completion_tokens=60, total_tokens=360)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(
            finish_reason=self.finish_reason, message=SimpleNamespace(content=text))])


# ----------------------------------------------------------------------------------------------
# Caso 1: modelo de chat guionado (misma idea que los fakes del tema 03).
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

CORRECT_SQL = """
SELECT r.name AS region, COUNT(*) AS retrasados
FROM orders o JOIN regions r ON r.region_id = o.region_id
WHERE o.promised_at >= '2026-03-01' AND o.promised_at < '2026-04-01'
AND (o.delivered_at > o.promised_at OR o.delivered_at IS NULL)
AND o.status != 'cancelado'
GROUP BY r.name ORDER BY retrasados DESC
"""


def reply(text="", calls=(), tokens=(100, 20)):
    usage = {"input_tokens": tokens[0], "output_tokens": tokens[1], "total_tokens": sum(tokens)}
    return AIMessage(content=text, usage_metadata=usage, tool_calls=[
        {"id": f"call-{index}-{name}", "name": name, "args": args} for index, (name, args) in enumerate(calls)])


class FakeChat(BaseChatModel):
    """Devuelve respuestas en orden y registra lo que recibió."""
    responses: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "doble-de-prueba"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self.bind(tool_names=[getattr(t, "name", str(t)) for t in tools], tool_choice=tool_choice)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        if not self.responses:
            raise AssertionError("El guion del modelo se agotó.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ChatResult(generations=[ChatGeneration(message=response)])
