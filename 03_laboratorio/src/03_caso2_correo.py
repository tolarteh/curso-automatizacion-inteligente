# %% [markdown]
# # Caso 2: un correo dispara la baja de un usuario en Git (LangGraph + aprobación humana)
#
# Objetivos: ver un flujo con ramas (enrutamiento), controles en código, una pausa real para
# aprobación humana (interrupt + checkpointer SQLite) y la verificación del estado final.
# Por qué LangGraph aquí: el flujo se detiene días esperando a dos personas, se reanuda
# donde quedó, tiene cinco finales distintos y las acciones escriben en un sistema.
# Ejecutar desde la raíz:
# `python 03_laboratorio\src\03_caso2_correo.py --backend groq`                 (buzón simulado)
# `python 03_laboratorio\src\03_caso2_correo.py --pendientes`
# `python 03_laboratorio\src\03_caso2_correo.py --aprobar correo-01_baja_clara s --aprobador "Diana (jefe)"`
# `python 03_laboratorio\src\03_caso2_correo.py --estado-git`

# %%
import json

import openai

import comun
from caso2_correo_langgraph.correo import MockMailbox
from caso2_correo_langgraph.extractor import LlmExtractor
from caso2_correo_langgraph.git_provider import FakeGitProvider
from caso2_correo_langgraph.grafo_baja import Contexto, build_graph
from caso2_correo_langgraph.trigger import (abrir_checkpointer, decidir, guardar_borrador, listar_pendientes,
                                            mostrar, procesar_correo)
from settings import DATA_CASO2, OUTPUTS_CASO2
from trazas_lc import Trace, TraceCallback, node_printer

ESTADO_GIT = OUTPUTS_CASO2 / "git_simulado.json"
CHECKPOINTS = OUTPUTS_CASO2 / "checkpoints.sqlite"
BORRADORES = OUTPUTS_CASO2 / "borradores"


def dependencias():
    git = FakeGitProvider(ESTADO_GIT, DATA_CASO2 / "git_inicial.json")
    talento = json.loads((DATA_CASO2 / "talento_humano.json").read_text(encoding="utf-8"))["radicados"]
    return git, talento


# %% [markdown]
# ## 1. Disparo: cada correo nuevo recorre el grafo en su propio hilo

# %%
def disparar(args, parse) -> int:
    backend = comun.backend_from(args, parse)
    trace = Trace("03_caso2_trigger", backend.name, backend.model)
    git, talento = dependencias()
    contexto = Contexto(git=git, talento=talento,
                        extractor=LlmExtractor(comun.chat_model(backend), [TraceCallback(trace, "caso2")]))
    fuente = MockMailbox(DATA_CASO2 / "buzon", solo=args.correo)
    trace.show("Fuente de correo", f"buzón simulado {fuente.carpeta}, modelo {backend.model}")
    checkpointer = abrir_checkpointer(CHECKPOINTS)
    app = build_graph(checkpointer)
    resultados = []
    try:
        for correo in fuente.nuevos():
            print(f"\nCorreo {correo.id}: «{correo.asunto}» de {correo.remitente}", flush=True)
            resultado = procesar_correo(app, correo, contexto, on_node=node_printer(trace))
            borrador = guardar_borrador(BORRADORES, resultado)
            trace.show(f"Resultado {resultado['thread_id']}", mostrar(resultado)
                       + (f"\n  borrador de respuesta (no se envía): {borrador}" if borrador else ""))
            trace.emit("correo", thread_id=resultado["thread_id"], estado=resultado["estado"],
                       ruta=resultado.get("ruta"), evaluacion=resultado.get("evaluacion"))
            resultados.append(resultado["estado"])
    except NotImplementedError:
        raise  # un TODO del reto: lo explica comun.ejecutar
    except (openai.OpenAIError, ValueError, RuntimeError, OSError) as exc:
        trace.show("ERROR", comun.explain(exc) + "\nEl correo quedó guardado: al repetir, el hilo se reanuda.")
        trace.end(completed=False, reason=type(exc).__name__, estados=resultados)
        return 2
    trace.end(completed=True, estados=resultados)
    return 0


# %% [markdown]
# ## 2. Aprobación humana: el grafo sigue donde se detuvo
#
# PR-TIC-004 exige dos aprobaciones registradas (jefe inmediato y seguridad). Cada
# `--aprobar <hilo> s` registra una y el grafo vuelve a detenerse hasta completar ambas;
# un `n` termina en RECHAZADO sin tocar el proveedor.

# %%
def aprobar(args) -> int:
    git, talento = dependencias()
    app = build_graph(abrir_checkpointer(CHECKPOINTS))
    trace = Trace("03_caso2_aprobacion", "ninguno", "ninguno")
    thread_id, decision = args.aprobar
    try:
        resultado = decidir(app, thread_id, decision, Contexto(git=git, talento=talento),
                            rol=args.rol, aprobador=args.aprobador, on_node=node_printer(trace))
    except ValueError as exc:
        trace.show("ERROR", str(exc))
        trace.end(completed=False, reason="aprobacion invalida")
        return 2
    borrador = guardar_borrador(BORRADORES, resultado)
    trace.show("Resultado", mostrar(resultado) + (f"\n  borrador de respuesta: {borrador}" if borrador else ""))
    trace.end(completed=True, thread_id=thread_id, estado=resultado["estado"])
    return 0


def pendientes() -> int:
    app = build_graph(abrir_checkpointer(CHECKPOINTS))
    items = listar_pendientes(app, app.checkpointer)
    if not items:
        print("No hay hilos pendientes de aprobación.")
    for item in items:
        print(mostrar(item) + "\n")
    return 0


def estado_git() -> int:
    git, _ = dependencias()
    data = git.estado()
    for login, cuenta in data["usuarios"].items():
        print(f"{login:13} {cuenta['estado']:9} tokens={len(cuenta['tokens'])} ssh={len(cuenta['llaves_ssh'])}")
    for nombre, repo in data["repositorios"].items():
        print(f"{nombre:21} " + ", ".join(f"{u}:{r}" for u, r in repo["miembros"].items()))
    print(f"Auditoría: {len(data['auditoria'])} cambios. Archivo: {ESTADO_GIT}")
    return 0


def reiniciar() -> int:
    """Vuelve al estado inicial: proveedor simulado, hilos y borradores (solo outputs/caso2)."""
    for path in (ESTADO_GIT, CHECKPOINTS, OUTPUTS_CASO2 / "checkpoints.sqlite-wal",
                 OUTPUTS_CASO2 / "checkpoints.sqlite-shm"):
        path.unlink(missing_ok=True)
    for path in BORRADORES.glob("*.txt") if BORRADORES.is_dir() else []:
        path.unlink()
    dependencias()
    print("Caso 2 reiniciado: proveedor Git simulado, hilos y borradores en su estado inicial.")
    return 0


def main() -> int:
    parse = comun.parser("Caso 2: baja de usuario en Git disparada por correo (LangGraph).")
    modo = parse.add_mutually_exclusive_group()
    modo.add_argument("--pendientes", action="store_true", help="Lista los hilos detenidos en aprobación.")
    modo.add_argument("--aprobar", nargs=2, metavar=("HILO", "S_N"), help="Decide un hilo pendiente: s o n.")
    modo.add_argument("--estado-git", action="store_true", help="Muestra el proveedor Git simulado.")
    modo.add_argument("--reiniciar", action="store_true", help="Restaura el estado inicial del caso.")
    modo.add_argument("--ver-grafo", action="store_true", help="Imprime el diagrama Mermaid y sale.")
    parse.add_argument("--correo", help="Solo este correo del buzón simulado (nombre sin extensión).")
    parse.add_argument("--rol", choices=("jefe_inmediato", "seguridad"), help="Por defecto, el siguiente pendiente.")
    parse.add_argument("--aprobador", default="", help="Nombre de quien decide (queda registrado).")
    args = parse.parse_args()
    if args.ver_grafo:
        print(build_graph().get_graph().draw_mermaid())
        return 0
    if args.pendientes:
        return pendientes()
    if args.estado_git:
        return estado_git()
    if args.reiniciar:
        return reiniciar()
    if args.aprobar:
        if not args.aprobador:
            parse.error("--aprobar exige --aprobador \"Nombre (rol)\": la decisión queda registrada.")
        return aprobar(args)
    return disparar(args, parse)


if __name__ == "__main__":
    raise SystemExit(comun.ejecutar(main))
