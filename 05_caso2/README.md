# Caso 2: baja controlada desde correo

El modelo extrae una solicitud; código valida identidad y fechas; dos personas revisan un plan concreto. Las acciones solo cambian un proveedor Git simulado en JSON. Correo e inventario son sintéticos. No hay conexión a Graph ni Git reales.

## Orden de trabajo

Preparar [el entorno](docs/preparacion.md) antes del laboratorio. Ejecutar comandos desde la raíz del repositorio, con el entorno común activo.

| Orden | Archivo en src | Objetivo | Resultado esperado al completar el reto |
|---|---|---|---|
| 1 | 01_eventos_y_validacion.py | Contrastar formulario y extracción de prosa | Campos con evidencia, sin acciones |
| 2 | 02_plan_y_aprobacion.py | Plan versionado y dos roles | Hash y acciones visibles, pausa persistente |
| 3 | 03_ejecucion_y_cierre.py | Ejecutar, verificar y reconciliar | Antes/después y cierre local |

```powershell
python 05_caso2\src\main.py
python 05_caso2\src\01_eventos_y_validacion.py
python 05_caso2\src\02_plan_y_aprobacion.py
python 05_caso2\src\03_ejecucion_y_cierre.py
python 05_caso2\tests\run_cpu.py --scaffold
python 05_caso2\tests\run_cpu.py
```

Los TODO esenciales fallan con NotImplementedError. No son fallos de instalación y no se ocultan como pruebas aprobadas. [Entrega y pistas](ENTREGA.md), [matriz de pruebas](docs/pruebas.md) y [MLflow](docs/mlflow.md).

## Recorrido operativo

1. Arrancar la API de correo y MLflow en terminales separadas según preparación.
2. Ingerir `mail-001`: formulario estructurado, cero llamadas al modelo.
3. Copiar `case_id`, hash y versión impresos. Revisar acciones y propietario único.
4. Aprobar una vez por rol con actores distintos. Ninguna aprobación ejecuta Git.
5. Ejecutar explícitamente con reloj de laboratorio.

```powershell
python 05_caso2\src\01_eventos_y_validacion.py --ingest --event mail-001 --today 2026-10-14
$case = Read-Host "case_id impreso"
$hash = Read-Host "hash del plan impreso"
python 05_caso2\src\02_plan_y_aprobacion.py --case $case --actor lider-demo --role manager --hash $hash --version 1
python 05_caso2\src\02_plan_y_aprobacion.py --case $case --actor seguridad-demo --role security --hash $hash --version 1
python 05_caso2\src\03_ejecucion_y_cierre.py --case $case --today 2026-10-14
```

El cierre queda en `outputs\cases\<case_id>\report.json`, `report.md` y `notification.txt`. El último es un borrador, nunca se envía. Transferencias de propietario son pendientes manuales y se declaran aunque los cambios automáticos se hayan comprobado.

## Controles y límites

Un ID de evento repetido se deduplica; el mismo ID con otro contenido produce conflicto. Otro ID puede corregir una solicitud, pero debe seguir coincidiendo con el registro de personal. Una versión válida nueva invalida el plan previo. Repetir una solicitud idéntica no prepara otra baja.

La política bloquea remitente no permitido, evidencia inventada, fecha futura e identidad contradictoria. El inventario completo participa en el hash. Un cambio externo, incluso en otro usuario, invalida aprobaciones. Esto es conservador a propósito.

Los actores de CLI son declarados, no autenticados. Allowlist no autentica al remitente. MLflow observa, no autoriza. JSON y checkpoints requieren un único escritor; un archivo lock impide procesos simultáneos. Tras un corte del proceso, revisar que no haya otro escritor antes de retirar el lock manualmente. No hay exactly-once ni garantía distribuida.

## Flujo tradicional, agente o híbrido

El formulario ya estructurado usa reglas y cero llamadas al LLM. En prosa libre el LLM puede recuperar campos sin exigir un formulario, pero puede inventarlos o rechazar mensajes válidos. Ambas rutas usan exactamente la misma política, plan y ejecutor.

Comparar extracción exacta y rechazo correcto contra `data\labels.json`, llamadas, tokens y latencia, usando mensajes equivalentes y el mismo reloj. No comparar solo respuestas finales. Para este corpus pequeño reportar conteos y errores, no prometer que el agente siempre mejora. Power Automate puede ejecutar pasos repetibles después de una decisión autorizada.

## Arquitectura

[HTML explorable](docs/arquitectura.html) y [archivo editable en draw.io](docs/diagramas/caso2_correo.drawio). La interfaz fija de Archify usa inglés; contenido del diagrama en español.

Las pruebas CPU no prueban calidad de extracción real, autenticidad de correo ni permisos institucionales.
