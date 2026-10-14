"""Una llamada real y acotada, sin fallback ni herramientas de escritura."""
import os
import time
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts import ALLOWLIST, ControlError, FIELDS, ROOT, digest


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    request_id: str = ""
    employee_id: str = ""
    username: str = ""
    effective_date: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)


def structured(body):
    lines = body.splitlines()
    if not lines or lines[0] != "BAJA":
        return None
    values = {}
    for line in lines[1:]:
        key, separator, value = line.partition("=")
        if not separator or key not in FIELDS or key in values or not value.strip():
            raise ControlError("Formulario estructurado inválido.")
        values[key] = value.strip()
    if set(values) != set(FIELDS):
        raise ControlError("Faltan campos del formulario.")
    return Extraction(intent="offboard", evidence=values.copy(), **values).model_dump()


def validate_evidence(event, extracted):
    if event["sender"] not in ALLOWLIST:
        raise ControlError("Remitente no permitido; allowlist no autentica identidad.")
    data = Extraction.model_validate(extracted).model_dump()
    if data["intent"] != "offboard":
        raise ControlError("El mensaje no es una solicitud válida de baja.")
    for key in FIELDS:
        value = data[key]
        evidence = data["evidence"].get(key, "")
        if not value or not evidence or evidence not in event["body"] or value != evidence:
            raise ControlError(f"Campo sin evidencia literal: {key}.")
    return data


def extract(event, provider=None):
    load_dotenv(ROOT / ".env", override=False)
    direct = structured(event["body"])
    if direct is not None:
        return direct, {"route": "traditional", "calls": 0, "tokens": 0, "latency_ms": 0}
    if event["sender"] not in ALLOWLIST:
        raise ControlError("Remitente no permitido.")
    if os.getenv("ALLOW_MODEL_CALLS") != "1":
        raise ControlError("Integración pendiente: autorizar inferencia y configurar modelo.")
    provider = provider or os.getenv("MODEL_PROVIDER", "groq")
    if provider == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ControlError("Falta GROQ_API_KEY.")
        url, model = "https://api.groq.com/openai/v1", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    elif provider == "local":
        key, url, model = "local", os.getenv("LOCAL_BASE_URL", "http://127.0.0.1:1234/v1"), os.getenv("LOCAL_MODEL")
        from urllib.parse import urlparse
        if urlparse(url).hostname not in {"127.0.0.1", "localhost"} or not model:
            raise ControlError("LM Studio exige URL loopback y LOCAL_MODEL explícito.")
    else:
        raise ControlError("Proveedor desconocido; no hay fallback.")
    prompt = (ROOT / "prompts" / "extract.txt").read_text(encoding="utf-8")
    client = ChatOpenAI(model=model, api_key=key, base_url=url, temperature=0, max_tokens=800, max_retries=0, timeout=30)
    start = time.perf_counter()
    response = client.invoke([("system", prompt), ("human", event["body"])])
    try:
        result = Extraction.model_validate_json(response.content).model_dump()
    except ValidationError as exc:
        raise ControlError("Respuesta del modelo fuera del contrato JSON; solicitud rechazada.") from exc
    stats = {"route": "hybrid", "calls": 1, "tokens": (response.usage_metadata or {}).get("total_tokens", 0),
             "latency_ms": (time.perf_counter() - start) * 1000, "provider": provider,
             "model": model, "prompt_hash": digest(prompt)}
    return result, stats
