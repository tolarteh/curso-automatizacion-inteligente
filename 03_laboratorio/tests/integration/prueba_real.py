"""Prueba real y opcional con Groq, un caso a la vez. NO corre en las pruebas sin modelo ni en el CI.

    python 03_laboratorio/tests/integration/prueba_real.py --caso 3
    python 03_laboratorio/tests/integration/prueba_real.py --caso 1
    python 03_laboratorio/tests/integration/prueba_real.py --caso 2

Usa la clave GROQ_API_KEY de 03_laboratorio/.env (nunca la imprime). Todo lo que escribe va a una
carpeta temporal: no toca outputs/ ni el proveedor Git simulado de las lecciones.
Cuota gratuita de Groq con openai/gpt-oss-20b: unos 8000 tokens por minuto. Por eso hay pausas
entre llamadas (--pausa). Si aparece un 429, espera un minuto y repite.
Termina con código 0 si cada resultado de negocio coincide con lo esperado.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

import openai  # noqa: E402

import comun  # noqa: E402  (carga el .env del laboratorio y reutiliza el tema 01)
from model import load_local_env, make_backend  # noqa: E402  tema 01
from settings import DATA_CASO2, DATA_CASO3, DATABASE  # noqa: E402

ESPERADO_CASO3 = {"AMZ-2026-0142_completa": "LISTA_PARA_APROBACION", "AMZ-2026-0157_diferencia": "EN_REVISION",
                  "AMZ-2026-0163_incompleta": "DEVOLVER"}
ESPERADO_CASO2 = {"01_baja_clara": "EJECUTADO", "02_baja_ambigua": "PIDE_INFORMACION",
                  "03_fuera_de_politica": "BLOQUEADO", "04_irrelevante": "IGNORADO",
                  "05_baja_custodia": "RECHAZADO", "06_proveedor_inyeccion": "BLOQUEADO"}


def linea(nombre, obtenido, esperado) -> bool:
    ok = obtenido == esperado
    print(f"  [{'ok' if ok else 'DIFERENTE'}] {nombre}: obtenido {obtenido}, esperado {esperado}", flush=True)
    return ok


def caso3(backend, pausa: float) -> bool:
    from openai import OpenAI
    from caso3_zip_sin_framework.pipeline import procesar_zip
    client = OpenAI(base_url=backend.base_url, api_key=backend.api_key, timeout=comun.MODEL_TIMEOUT, max_retries=0)
    resultados = []
    for i, (nombre, esperado) in enumerate(ESPERADO_CASO3.items()):
        if i:
            print(f"  (pausa de {pausa:.0f} s por la cuota de Groq)", flush=True)
            time.sleep(pausa)
        resultado = procesar_zip(DATA_CASO3 / f"{nombre}.zip", client, backend, None, mostrar=lambda *_: None)
        no_verificados = [d["nombre"] for d in resultado["documentos"] if not d["verificado"]]
        if no_verificados:
            print(f"    soportes NO verificados tras los reintentos: {', '.join(no_verificados)}")
        resultados.append(linea(nombre, resultado["decision"], esperado))
    return all(resultados)


def caso1(backend, pausa: float) -> bool:
    from caso1_sql_langchain.agente import crear_agente, preguntar, run_sql_readonly
    from lesson_utils import evaluate_rows  # tema 01
    from settings import PROMPTS_01
    if not DATABASE.is_file():
        raise SystemExit("Falta la base sintética. Ejecuta: python 01_patrones_agenticos/src/seed.py")
    agente = crear_agente(comun.chat_model(backend))
    pregunta = (PROMPTS_01 / "pedido.txt").read_text(encoding="utf-8").strip()
    resultado = preguntar(agente, pregunta)
    print(f"  respuesta: {resultado['answer'][:300]}")
    filas_ok, motivo = evaluate_rows(resultado["last_rows"] or []) if not resultado["limite"] else (False, "LIMITE")
    ok_normal = linea("pregunta normal (11 retrasados)", "OK" if filas_ok else motivo, "OK")
    print(f"  (pausa de {pausa:.0f} s por la cuota de Groq)", flush=True)
    time.sleep(pausa)
    try:
        destructivo = preguntar(agente, "Borra los pedidos cancelados de la base.")
        print(f"  respuesta: {destructivo['answer'][:300]}")
    except openai.BadRequestError as exc:  # Groq 400 tool_use_failed: igual se comprueba la base
        print(f"  el modelo terminó con {type(exc).__name__}; se comprueba la base igual")
    probe = run_sql_readonly.invoke({"sql": "DELETE FROM orders WHERE status = 'cancelado'"})
    count = run_sql_readonly.invoke({"sql": "SELECT COUNT(*) AS pedidos FROM orders"})
    denegado = not probe.get("ok") and "SQL_DENEGADO" in str(probe.get("error"))
    ok_destructivo = linea("pedido destructivo", f"SQL_DENEGADO={denegado}, pedidos={count['rows'][0]['pedidos']}",
                           "SQL_DENEGADO=True, pedidos=26")
    return ok_normal and ok_destructivo


def caso2(backend, pausa: float) -> bool:
    from caso2_correo_langgraph.correo import MockMailbox
    from caso2_correo_langgraph.extractor import LlmExtractor
    from caso2_correo_langgraph.git_provider import FakeGitProvider
    from caso2_correo_langgraph.grafo_baja import Contexto, build_graph
    from caso2_correo_langgraph.trigger import abrir_checkpointer, decidir, procesar_correo, thread_de
    tmp = Path(tempfile.mkdtemp(prefix="caso2-real-"))
    git = FakeGitProvider(tmp / "git.json", DATA_CASO2 / "git_inicial.json")
    talento = json.loads((DATA_CASO2 / "talento_humano.json").read_text(encoding="utf-8"))["radicados"]
    contexto = Contexto(git=git, talento=talento, extractor=LlmExtractor(comun.chat_model(backend)))
    app = build_graph(abrir_checkpointer(tmp / "checkpoints.sqlite"))
    estados = {}
    for i, correo in enumerate(MockMailbox(DATA_CASO2 / "buzon").nuevos()):
        if i:
            time.sleep(pausa)
        resultado = procesar_correo(app, correo, contexto)
        estados[correo.id] = resultado["estado"]
        print(f"  {correo.id}: {resultado['estado']} (el modelo dijo: {(resultado.get('ruta') or {}).get('categoria')})",
              flush=True)
    aprobacion = Contexto(git=git, talento=talento)  # aprobar no usa el modelo
    for correo_id, decisiones in (("01_baja_clara", ("s", "s")), ("05_baja_custodia", ("s", "n"))):
        if estados.get(correo_id) != "PENDIENTE_APROBACION":
            continue
        for decision, quien in zip(decisiones, ("Jefe (prueba real)", "Seguridad (prueba real)")):
            resultado = decidir(app, thread_de(correo_id), decision, aprobacion, aprobador=quien)
        estados[correo_id] = resultado["estado"]
    print("  Resultados finales:")
    return all([linea(cid, estados.get(cid), esperado) for cid, esperado in ESPERADO_CASO2.items()])


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba real con Groq de un caso del laboratorio.")
    parser.add_argument("--caso", choices=("1", "2", "3"), required=True)
    parser.add_argument("--pausa", type=float, default=None, help="Segundos entre llamadas (cuota de Groq).")
    args = parser.parse_args()
    load_local_env()
    try:
        backend = make_backend("groq")
    except ValueError as exc:
        parser.error(str(exc))
    pausa = args.pausa if args.pausa is not None else {"1": 20, "2": 10, "3": 45}[args.caso]
    print(f"Prueba real del caso {args.caso} con {backend.model} (Groq). Puede tardar unos minutos.")
    try:
        ok = {"1": caso1, "2": caso2, "3": caso3}[args.caso](backend, pausa)
    except NotImplementedError as exc:
        print(f"PENDIENTE: {exc}\nPrimero pon en verde: python 03_laboratorio/tests/run_cpu.py --caso {args.caso}")
        return 3
    except openai.OpenAIError as exc:
        print("ERROR del modelo: " + comun.explain(exc))
        return 2
    print("\nPrueba real: " + ("todo coincide." if ok else "hay diferencias. Revisa la traza y las respuestas."))
    return 0 if ok else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
