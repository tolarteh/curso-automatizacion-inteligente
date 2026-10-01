import argparse
from dataclasses import dataclass
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from settings import TOPIC


def local_url(url: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("El endpoint local debe usar loopback, sin credenciales ni parámetros en la URL.")
    return url


def load_local_env() -> None:
    path = TOPIC / ".env"
    if path.is_file():
        with path.open(encoding="utf-8") as stream:
            load_dotenv(stream=stream, override=False)


@dataclass(frozen=True)
class Backend:
    name: str
    base_url: str
    model: str
    api_key: str
    reasoning_effort: str | None


def make_backend(name: str) -> Backend:
    if name == "local":
        return Backend(name, local_url(os.environ.get("LOCAL_BASE_URL", "http://localhost:1234/v1")),
                       os.environ.get("LOCAL_MODEL", "demo-local"), "lm-studio",
                       os.environ.get("LOCAL_REASONING_EFFORT", "none") or None)
    if name == "groq":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        if not key or urlparse(url).scheme != "https":
            raise ValueError("Groq requiere clave y HTTPS.")
        return Backend(name, url, os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"), key,
                       os.environ.get("GROQ_REASONING_EFFORT", "low") or None)
    raise ValueError(f"Backend desconocido: {name}")


def start(description: str, extra=None):
    load_local_env()
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--backend", choices=("local", "groq"),
                        default=os.environ.get("LLM_BACKEND", "local"))
    if extra:
        extra(parser)
    args = parser.parse_args()
    try:
        return args, make_backend(args.backend)
    except ValueError as exc:
        parser.error(str(exc))
