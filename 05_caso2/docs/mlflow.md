# MLflow: leer la trayectoria

## Qué registra

Run: segmento de ingesta, aprobación, replanificación o ejecución. Ningún run permanece abierto esperando a una persona. FINISHED significa que ese segmento acabó técnicamente; `business_status=PENDIENTE_APROBACION` no significa baja terminada.

Params: proveedor/modelo cuando hubo LLM, hash de prompt, límite de llamadas y nivel. Metrics: llamadas, tokens, latencia, duración, acciones propuestas/comprobadas y aprobaciones. Tags: case_id, thread_id, hash/versión del plan y estado de negocio. El diario y el checkpoint son la fuente de estado y evidencia; el dashboard no otorga permisos.

Por defecto metrics no registra cuerpo del correo, nombres personales, credenciales ni estado completo. Spans explícitos muestran extraction, policy, planning, human_approval y execute_and_verify con identificadores y hashes, no payloads. La cuenta que escribe en MLflow es distinta del actor declarado que aprueba.

Con `SYNTHETIC_TRACES=1` y `--level traces`, el autolog de LangChain captura el recorrido de LangGraph y llamadas al modelo. Puede guardar entradas/salidas completas: solo datos sintéticos. Se desactiva al cerrar cada segmento. No activar autolog global fuera de este contexto.

## Ejercicio en el visor

1. Abrir experimento `synthetic-offboarding`, ordenar runs por hora y filtrar case_id.
2. Revisar Params, Metrics y Tags de la ingesta. ¿Hubo llamada al modelo o formulario?
3. Abrir Traces. En metrics inspeccionar spans sanitizados; en traces expandir nodo y entrada/salida sintética. No confundir un span con un permiso.
4. Comparar aprobación 1 y 2: mismo hash, roles distintos en auditoría local, cero escritura Git.
5. Abrir segmento execution y contrastar actions_verified con report.json. Los reportes son artifacts locales del caso, no se suben automáticamente a MLflow para evitar payloads accidentales.

## Tres investigaciones

- Extracción rechazada: ejecutar correo con remitente ajeno; localizar span policy/extraction y run FAILED. Identificar primer control que falló, no cambiar el prompt sin evidencia.
- Inventario cambió tras aprobar: añadir un equipo sintético en outputs\git.json. La ejecución debe invalidar el plan. Revisar segmento FAILED y PLAN_INVALIDADO, luego replan y hash nuevo.
- Fallo parcial: inyectar `--fail-after 2`, revisar dos acciones comprobadas y pendientes. Reanudar; comparar segmentos por case_id y hash.

Un error de tracking es un error operativo visible. Si una acción ya ocurrió y falló el registro remoto, no se revierte mágicamente: revisar diario y estado local antes de reanudar.

## Referencias usadas

- [Tracing de LangGraph con MLflow](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/langgraph/)
- [Autenticación MLflow](https://mlflow.org/docs/latest/self-hosting/security/basic-http-auth/)
- [Interrupts y reanudación LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts)

La integración usa mlflow.langchain.autolog y SqliteSaver. Los spans explícitos cubren controles sin LLM y el modo sanitizado. Verificar compatibilidad al actualizar las versiones fijadas del manifest.
