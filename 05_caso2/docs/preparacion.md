# Preparación

## Entorno común

Desde la raíz del repositorio, usar el entorno Python del curso. No crear un entorno por tema.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
Copy-Item 05_caso2\.env.example 05_caso2\.env
```

Editar el `.env` del tema. Las variables del proceso tienen prioridad. No registrar `.env`, outputs, contraseñas ni trazas en Git.

## Servicios locales

Terminal 1:

```powershell
python 05_caso2\src\events.py
```

La API solo escucha loopback, entrega páginas de dos mensajes y no cambia leído/no leído. No envía mensajes.

Terminal 2: configurar usuario y contraseña de laboratorio (mínimo 16 caracteres) y `MLFLOW_FLASK_SERVER_SECRET_KEY` privada y estable en `.env`. El script crea configuración con contraseña en texto plano dentro de outputs. Proteger esta carpeta con permisos del sistema y eliminarla al terminar el laboratorio.

```powershell
python 05_caso2\src\mlflow_server.py
```

Abrir `http://127.0.0.1:5005` y autenticarse con esos datos. La cuenta de laboratorio es administradora local, no identidad de quien aprueba. Nunca exponer este servidor a la red. Cerrar ambas terminales con Ctrl+C.

## Modelos reales, opt-in

Groq es el proveedor predeterminado. Definir `GROQ_API_KEY`, modelo y `ALLOW_MODEL_CALLS=1` solo después de autorización para consumir cuota y transmitir texto sintético. No pegar mensajes reales. Seleccionar `--event mail-002` para prosa libre.

LM Studio requiere servidor loopback ya preparado, modelo cargado explícitamente, `LOCAL_MODEL` exacto y `--provider local`. No carga modelos automáticamente. No hay fallback.

```powershell
python 05_caso2\src\01_eventos_y_validacion.py --ingest --event mail-002 --provider local --today 2026-10-14
```

Sin autorización o sin configuración el programa falla explícitamente. Usar `mail-001` no necesita inferencia.

## Reinicio y fallos

Los datos fuente no se modifican. `outputs\git.json` es el estado del Git simulado. `outputs\cases` guarda planes, aprobaciones, diario y reportes. `checkpoints.sqlite` conserva pausas. `events.sqlite` conserva identidad de eventos.

Para repetir desde cero, detener todos los procesos y retirar únicamente outputs del tema. Conservar antes la evidencia que se quiera comparar. No borrar checkpoints para "resolver" una autorización fallida.

Cambiar inventario invalida plan. Tras detectar `PLAN_INVALIDADO`:

```powershell
python 05_caso2\src\02_plan_y_aprobacion.py --case $case --replan --today 2026-10-14
```

Copiar nuevo hash y versión; obtener dos aprobaciones nuevas. Para fallo parcial:

```powershell
python 05_caso2\src\03_ejecucion_y_cierre.py --case $case --today 2026-10-14 --fail-after 2
python 05_caso2\src\03_ejecucion_y_cierre.py --case $case --today 2026-10-14
```

El primer comando debe fallar con reporte PARCIAL. Extensión: `--crash-after-change 1`. El corte se inyecta como excepción visible para estudiar reconciliación; no mata procesos ni servicios.
