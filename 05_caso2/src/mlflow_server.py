"""Arranque explícito de servidor local autenticado, sin Docker."""
import os
import subprocess
import sys
from dotenv import load_dotenv
from contracts import ControlError, ROOT


if __name__ == "__main__":
    load_dotenv(ROOT / ".env", override=False)
    username = os.getenv("MLFLOW_TRACKING_USERNAME", "")
    password = os.getenv("MLFLOW_TRACKING_PASSWORD", "")
    if not username or len(password) < 16 or any(char in username + password for char in "\r\n%"):
        raise ControlError("Configurar usuario y contraseña local de 16 caracteres, sin %, CR ni LF.")
    output = ROOT / "outputs" / "mlflow"
    output.mkdir(parents=True, exist_ok=True)
    config = output / "auth.ini"
    config.write_text(
        "[mlflow]\ndefault_permission = NO_PERMISSIONS\n"
        f"database_uri = sqlite:///{(output / 'auth.db').as_posix()}\n"
        f"admin_username = {username}\nadmin_password = {password}\n"
        "authorization_function = mlflow.server.auth:authenticate_request_basic_auth\n",
        encoding="utf-8")
    env = dict(os.environ, MLFLOW_AUTH_CONFIG_PATH=str(config))
    if not env.get("MLFLOW_FLASK_SERVER_SECRET_KEY"):
        raise ControlError("Configurar MLFLOW_FLASK_SERVER_SECRET_KEY estable y privado.")
    command = [sys.executable, "-m", "mlflow", "server", "--app-name", "basic-auth",
               "--host", "127.0.0.1", "--port", "5005", "--backend-store-uri",
               f"sqlite:///{(output / 'tracking.db').as_posix()}",
               "--default-artifact-root", (output / "artifacts").as_uri()]
    print("MLflow autenticado en http://127.0.0.1:5005, cerrar con Ctrl+C.")
    subprocess.run(command, env=env, check=True)
