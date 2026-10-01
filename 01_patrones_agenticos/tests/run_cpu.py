"""Ejecuta las pruebas sin permitir conexiones ni resolución de nombres."""
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch


def main() -> int:
    directory = Path(__file__).resolve().parent
    with ExitStack() as stack:
        for name in ("socket.create_connection", "socket.socket.connect",
                     "socket.socket.connect_ex", "socket.getaddrinfo"):
            stack.enter_context(patch(name, side_effect=AssertionError(
                "Las pruebas CPU no pueden usar red ni modelos reales.")))
        suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
