"""Pruebas del laboratorio sin red ni modelo (este programa bloquea la red).

    python 03_laboratorio/tests/run_cpu.py --caso 3     # aceptación del caso 3 (sin framework)
    python 03_laboratorio/tests/run_cpu.py --caso 1     # aceptación del caso 1 (LangChain)
    python 03_laboratorio/tests/run_cpu.py --caso 2     # aceptación del caso 2 (LangGraph)
    python 03_laboratorio/tests/run_cpu.py --andamiaje  # lo que ya viene hecho (debe estar en verde)
    python 03_laboratorio/tests/run_cpu.py              # todo
    python 03_laboratorio/tests/run_cpu.py --ci         # CI: andamiaje en verde; en aceptación solo se
                                                        # aceptan pruebas en verde o PENDIENTES (TODO)

Cada prueba termina en una de cuatro marcas:
    [ok]         cumple el resultado de negocio.
    [PENDIENTE]  llegó a un TODO del reto (NotImplementedError): el mensaje dice cuál.
    [FALLA]      hay implementación, pero el resultado no es el esperado: el mensaje dice qué se esperaba.
    [ERROR]      excepción inesperada: se muestra el tipo, el mensaje y la línea de src/ donde ocurrió.
Con --detalle se imprime la traza completa de FALLA y ERROR.
"""
import argparse
from contextlib import ExitStack
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

DIRECTORY = Path(__file__).resolve().parent
SRC = DIRECTORY.parent / "src"
CASOS = {
    "1": ("Caso 1 · asistente SQL de solo lectura (LangChain create_agent)", "test_caso1.py"),
    "2": ("Caso 2 · correo → baja en Git con aprobación humana (LangGraph)", "test_caso2.py"),
    "3": ("Caso 3 · soportes de amortización en ZIP (sin framework)", "test_caso3.py"),
}
ANDAMIAJE = ("Andamiaje · lo que ya viene hecho", "test_andamiaje.py")


def pendiente(err) -> NotImplementedError | None:
    """El NotImplementedError del TODO, aunque venga envuelto por LangGraph o LangChain."""
    exc, seen = err[1], set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, NotImplementedError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


def lugar(err) -> str:
    """La última línea de src/ (o de la prueba) donde ocurrió el problema."""
    frames = traceback.extract_tb(err[2])
    for frame in reversed(frames):
        if str(SRC) in frame.filename:
            return f"{Path(frame.filename).relative_to(SRC.parent).as_posix()}:{frame.lineno}"
    for frame in reversed(frames):
        if str(DIRECTORY) in frame.filename:
            return f"{Path(frame.filename).relative_to(DIRECTORY.parent).as_posix()}:{frame.lineno}"
    return ""


class Resultado(unittest.TestResult):
    def __init__(self, detalle=False):
        super().__init__()
        self.detalle = detalle
        self.filas = []        # (marca, prueba, texto)
        self.todos = []        # mensajes de TODO pendientes, sin repetir

    @staticmethod
    def nombre(test) -> str:
        doc = test.shortDescription()
        return doc or test.id().split(".")[-1]

    def addSuccess(self, test):
        super().addSuccess(test)
        self._fila("ok", test, "")

    def _clasificar(self, test, err, marca):
        todo = pendiente(err)
        if todo is not None:
            mensaje = str(todo) or "TODO sin mensaje"
            if mensaje in self.todos:  # ya se explicó arriba: solo se nombra
                self._fila("PENDIENTE", test, "mismo TODO: " + mensaje.split(":")[0])
            else:
                self.todos.append(mensaje)
                self._fila("PENDIENTE", test, mensaje)
            return
        exc = err[1]
        texto = f"{exc}" if marca == "FALLA" else f"{type(exc).__name__}: {exc}"
        texto = texto.strip().splitlines()[0] if texto.strip() else type(exc).__name__
        donde = lugar(err)
        self._fila(marca, test, texto + (f"  ({donde})" if donde else ""))
        if self.detalle:
            print("".join(traceback.format_exception(*err)))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._clasificar(test, err, "FALLA")

    def addError(self, test, err):
        super().addError(test, err)
        self._clasificar(test, err, "ERROR")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._clasificar(subtest, err, "FALLA" if issubclass(err[0], AssertionError) else "ERROR")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._fila("omitida", test, reason)

    def _fila(self, marca, test, texto):
        self.filas.append((marca, test, texto))
        etiqueta = f"[{marca}]".ljust(12)
        print(f"  {etiqueta}{self.nombre(test)}" + (f"\n{'':14}→ {texto}" if texto else ""), flush=True)

    def cuenta(self, marca) -> int:
        return sum(1 for fila in self.filas if fila[0] == marca)


def correr(titulo: str, archivo: str, detalle: bool) -> Resultado:
    print(f"\n{titulo}  ({archivo})")
    suite = unittest.defaultTestLoader.discover(str(DIRECTORY), pattern=archivo)
    resultado = Resultado(detalle)
    suite.run(resultado)
    print(f"  Resumen: {resultado.cuenta('ok')} ok · {resultado.cuenta('PENDIENTE')} pendientes · "
          f"{resultado.cuenta('FALLA')} fallas · {resultado.cuenta('ERROR')} errores")
    if resultado.todos:
        print("  TODO por resolver (en el orden en que las pruebas los encontraron):")
        for mensaje in resultado.todos:
            print(f"    - {mensaje}")
    return resultado


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pruebas del laboratorio 03 sin red ni modelo.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--caso", choices=sorted(CASOS), help="Solo las pruebas de aceptación de ese caso.")
    grupo.add_argument("--andamiaje", action="store_true", help="Solo lo que ya viene hecho.")
    grupo.add_argument("--ci", action="store_true",
                       help="Andamiaje en verde; en aceptación se aceptan ok y PENDIENTE, nunca FALLA ni ERROR.")
    parser.add_argument("--detalle", action="store_true", help="Traza completa de FALLA y ERROR.")
    args = parser.parse_args(argv)

    if args.caso:
        grupos = [CASOS[args.caso]]
    elif args.andamiaje:
        grupos = [ANDAMIAJE]
    else:
        grupos = [ANDAMIAJE, *(CASOS[k] for k in ("3", "1", "2"))]

    with ExitStack() as stack:
        for name in ("socket.create_connection", "socket.socket.connect",
                     "socket.socket.connect_ex", "socket.getaddrinfo"):
            stack.enter_context(patch(name, side_effect=AssertionError(
                "Las pruebas CPU no pueden usar red ni modelos reales.")))
        resultados = [(archivo, correr(titulo, archivo, args.detalle)) for titulo, archivo in grupos]

    def limpio(resultado, permitir_pendientes):
        malas = resultado.cuenta("FALLA") + resultado.cuenta("ERROR")
        return malas == 0 and (permitir_pendientes or resultado.cuenta("PENDIENTE") == 0)

    if args.ci:
        ok = all(limpio(r, permitir_pendientes=(archivo != ANDAMIAJE[1])) for archivo, r in resultados)
        print("\nCI: " + ("el andamiaje está en verde y el reto solo tiene pruebas en verde o PENDIENTES."
                          if ok else "hay fallas o errores que no son TODO del reto."))
        return 0 if ok else 1
    ok = all(limpio(r, permitir_pendientes=False) for _, r in resultados)
    if args.caso:
        print("\nTerminado (sin modelo): todas las pruebas del caso en verde. Falta la corrida real con Groq "
              "(ver README)." if ok else "\nAún no: resuelve los PENDIENTES de arriba en orden y vuelve a correr.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
