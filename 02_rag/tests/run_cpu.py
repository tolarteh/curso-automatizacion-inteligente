"""Pruebas CPU con conexiones y DNS bloqueados, sin modelos reales."""
from pathlib import Path
import socket
import unittest
from unittest.mock import patch


def blocked(*args, **kwargs):
    raise AssertionError("Las pruebas CPU no pueden usar red ni modelos reales.")


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    with patch.object(socket, "create_connection", blocked), \
         patch.object(socket.socket, "connect", blocked), \
         patch.object(socket.socket, "connect_ex", blocked), \
         patch.object(socket, "getaddrinfo", blocked):
        suite = unittest.defaultTestLoader.discover(str(folder))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
