"""Borra el estado operativo del laboratorio, sin tocar MLflow ni datos fuente."""
import shutil
import stat

from contracts import ControlError
from service import OUTPUT, exclusive

TARGETS = (
    "cases", "events.sqlite", "events.sqlite-wal", "events.sqlite-shm",
    "events.sqlite-journal", "checkpoints.sqlite", "checkpoints.sqlite-wal",
    "checkpoints.sqlite-shm", "checkpoints.sqlite-journal", "git.json", "git.json.new",
)


def reset_state():
    with exclusive():
        paths = [OUTPUT / name for name in TARGETS]
        for path in paths:
            if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ControlError(f"No se elimina un enlace: {path}")
            if path.exists() and (path.is_dir() != (path.name == "cases")):
                raise ControlError(f"Tipo de ruta inesperado: {path}")
        for path in paths:
            if not path.exists():
                continue
            if path.name == "cases":
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"Eliminado: {path.name}")


def main():
    print("REINICIO DESTRUCTIVO del laboratorio sintético.")
    print(f"Ubicación: {OUTPUT}")
    print("Borra casos, eventos, checkpoints y Git sintético, sin respaldo.")
    print("Conserva MLflow, .env, datos fuente, pruebas y respaldos anteriores.")
    print("El inventario inicial se recrea en la siguiente ingesta.")
    if input("Escribe REINICIAR para confirmar: ").strip() != "REINICIAR":
        print("Reinicio cancelado, sin cambios.")
        return
    reset_state()
    print("Estado operativo eliminado. Puedes volver a ingerir los mismos correos.")


if __name__ == "__main__":
    main()
