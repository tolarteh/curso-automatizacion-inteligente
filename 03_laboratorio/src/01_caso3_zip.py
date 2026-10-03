# %% [markdown]
# # Caso 3: soportes de amortización en un ZIP, sin framework
#
# Objetivos: ver que no todo es un agente. Cuando los pasos son siempre los mismos, un
# cadena de pasos fija en Python plano basta: el modelo solo convierte texto en campos y las
# reglas de PR-FIN-012 (en código) deciden. Patrones: orquestación (un trabajador por
# documento) y evaluador-optimizador acotado (reglas → reintento, máximo 2 intentos).
# Ejecutar desde la raíz:
# `python 03_laboratorio\src\01_caso3_zip.py --backend groq`
# `python 03_laboratorio\src\01_caso3_zip.py --backend groq --zip AMZ-2026-0163_incompleta`

# %%
from pathlib import Path

import openai
from openai import OpenAI

import comun
from caso3_zip_sin_framework.pipeline import guardar, procesar_zip
from caso3_zip_sin_framework.zip_seguro import ZipRechazado
from settings import DATA_CASO3, OUTPUTS_CASO3
from trace_log import Trace  # tema 01: mismo formato JSONL y enmascarado de secretos

ESPERADO = {"AMZ-2026-0142_completa": "LISTA_PARA_APROBACION", "AMZ-2026-0157_diferencia": "EN_REVISION",
            "AMZ-2026-0163_incompleta": "DEVOLVER"}


def ruta_zip(valor: str) -> Path:
    path = Path(valor)
    if path.suffix.lower() != ".zip":
        path = DATA_CASO3 / f"{valor}.zip"
    return path


# %% [markdown]
# ## 1. La cadena de pasos: pasos fijos, un for y reglas
#
# Abrir el ZIP de forma segura → extraer texto → un trabajador por soporte (modelo con
# JSON Schema) → evaluar con reglas y reintentar → decidir con PR-FIN-012 → resumen con
# SHA-256. Ver caso3_zip_sin_framework/pipeline.py.

# %%
def main() -> int:
    parse = comun.parser("Caso 3: soportes de amortización en un ZIP, cadena de pasos sin framework.")
    parse.add_argument("--zip", default="AMZ-2026-0142_completa",
                       help="Nombre de un ZIP de data/caso3 (sin .zip) o ruta a un ZIP.")
    args = parse.parse_args()
    path = ruta_zip(args.zip)
    if not path.is_file():
        parse.error(f"No existe el ZIP {path}. Disponibles: {', '.join(ESPERADO)}")
    backend = comun.backend_from(args, parse)
    client = OpenAI(base_url=backend.base_url, api_key=backend.api_key, timeout=comun.MODEL_TIMEOUT, max_retries=0)
    trace = Trace("03_caso3_zip", backend.name, backend.model)
    trace.show("ZIP", str(path))
    try:
        resultado = procesar_zip(path, client, backend, trace)
    except (ZipRechazado, ValueError, openai.OpenAIError) as exc:
        trace.show("ERROR", comun.explain(exc))
        trace.end(completed=False, reason=type(exc).__name__)
        return 2
    json_path, md_path = guardar(resultado, OUTPUTS_CASO3)
    trace.show("Decisión sugerida (la aprobación es de una persona)",
               resultado["decision"] + "".join(f"\n- {m}" for m in resultado["motivos"] + resultado["observaciones"]))
    trace.show("Resumen trazable", f"{md_path}\n{json_path}")

    # ## 2. Comprobación: la decisión esperada de cada ZIP sintético no depende del modelo
    esperado = ESPERADO.get(path.stem)
    ok = esperado is None or resultado["decision"] == esperado
    if esperado:
        trace.show("Comprobación", f"esperado {esperado}, obtenido {resultado['decision']}: {'OK' if ok else 'FALLA'}")
    trace.end(completed=True, decision=resultado["decision"], esperado=esperado, verificado=ok)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(comun.ejecutar(main))
