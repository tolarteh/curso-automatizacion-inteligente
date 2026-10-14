# %% [markdown]
# # Eventos y validación
#
# Objetivos: distinguir evento y solicitud; comprobar evidencia; comparar
# formulario determinista y prosa libre. Prerrequisitos: Python, HTTP y JSON.
# Ejecutar: python 05_caso2\src\01_eventos_y_validacion.py
# Para ingesta HTTP: añadir --ingest --today 2026-10-14.
#
# Intuición: recibir dos veces el mismo correo no crea dos autorizaciones.
# El modelo interpreta prosa, no autentica remitentes ni autoriza la baja.

# %%
import argparse
import json
from contracts import ROOT, read_json
from events import fetch_events
from extraction import structured, validate_evidence


def demo():
    event = read_json(ROOT / "data" / "messages.json")[0]
    fields = structured(event["body"])
    print("Ruta tradicional, llamadas al modelo: 0")
    print(json.dumps(fields, indent=2, ensure_ascii=False))
    validated = validate_evidence(event, fields)
    assert validated["username"] == "ana.dev"
    print("Evidencia comprobada, todavía sin permiso de ejecución.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--today", default="2026-10-14")
    parser.add_argument("--provider", choices=["groq", "local"])
    parser.add_argument("--event", default="mail-001")
    parser.add_argument("--level", choices=["metrics", "traces"], default="metrics")
    args = parser.parse_args()
    if args.ingest:
        from service import ingest
        events = fetch_events()
        event = next(event for event in events if event["id"] == args.event)
        case = ingest(event, args.today, args.level, args.provider)
        print(json.dumps(case, indent=2, ensure_ascii=False))
    else:
        demo()

# %% [markdown]
# ## Comprobación y paso a producción
#
# Un campo sin fragmento literal se rechaza. Para prosa libre se usa una llamada
# real con límite de tokens, sin herramientas de escritura ni fallback.
# Graph real necesita identidad de tenant, consentimiento y política de correo.
# Allowlist y API loopback no prueban identidad.
#
# Recapitulación: evento no es solicitud; evidencia no es autorización;
# extracción errónea se mide con etiquetas y controles independientes.
