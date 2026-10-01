# Patrones agénticos

## Recorrido

| Lección | Objetivo | Comando desde la raíz |
|---|---|---|
| [Reflection](src/01_reflection.py) | Separar crítica del modelo y verificación de resultados | `python 01_patrones_agenticos\src\01_reflection.py` |
| [Tool use](src/02_tool_use.py) | Seguir las solicitudes y comprobar permisos fuera del prompt | `python 01_patrones_agenticos\src\02_tool_use.py` |
| [Planning](src/03_planning.py) | Validar un plan y detenerlo en la revisión humana | `python 01_patrones_agenticos\src\03_planning.py` |

Reflection imprime el SQL inicial, las filas, cada crítica y la comprobación final. Si el primer SQL ya es correcto, puede no haber correcciones. Si los conteos finales no coinciden, termina con código 2; no presenta esa ejecución como aprobada.

Tool use imprime cada resultado y comprueba las filas de la última consulta. Está limitado a tres llamadas, cinco turnos, dos errores consecutivos y 90 segundos de presupuesto. `--case destructivo` contrasta la petición de borrado con el rechazo real de la herramienta, sobre los datos sintéticos.

El [contrato de planificación](src/planning_contract.py) distingue software, modelo y persona. Valida campos, tipos, orden y herramientas permitidas, y exige que el informe termine en revisión humana. Un JSON sintácticamente válido no implica que el plan se pueda ejecutar.

Planning imprime el plan, los resultados verificados y el resumen antes de solicitar aprobación. `--aprobar n` permite comprobar el rechazo sin interacción; `--aprobar s` registra una decisión explícita del operador. Ninguna opción envía un informe. Un rechazo es un resultado esperado del control, no un permiso para continuar.

## Datos y referencia

El ejemplo usa 26 pedidos sintéticos de cinco regiones. El informe incluye pedidos con fecha prometida en marzo de 2026, al corte del 5 de abril.

Un pedido está retrasado si se entregó después de la fecha prometida o sigue sin entregar al corte. Se excluyen los cancelados. El resultado esperado es 11 retrasados: Cundinamarca 5, Antioquia 3, Valle del Cauca 2 y Atlántico 1.

La referencia está en [data/fixtures/expected.json](data/fixtures/expected.json). El generador calcula el mismo resultado en Python, sin SQL ni modelo.

## Preparación

Usar el entorno común explicado en el [README raíz](../README.md). Desde la raíz del repositorio:

```powershell
python 01_patrones_agenticos\src\seed.py
```

Las dependencias del cliente real están en el manifest raíz:

```powershell
python -m pip install -r requirements.txt
python -m pip check
```

Para configurar modelos, copiar [.env.example](.env.example) a `.env` en la raíz de este tema. Las variables de la terminal tienen prioridad. El backend local requiere LM Studio con su servidor habilitado y un modelo que admita herramientas y JSON Schema, identificado como `demo-local`. LM Studio y los modelos se instalan aparte.

`LOCAL_REASONING_EFFORT=none` corresponde al modelo usado en el ejemplo. Para otro modelo, revisar los parámetros que soporta; dejar ese valor vacío evita enviar el parámetro.

Groq usa el mismo cliente compatible con OpenAI, pero requiere salida a internet, clave y cuota. Se elige con `--backend groq` o configurando `LLM_BACKEND` expresamente. No se usa como respaldo automático del modelo local.

La base se guarda en `outputs`, ignorado por Git. Si ya existe, el comando no la sobrescribe. `--reset` solo reemplaza una base que conserve el marcador de datos sintéticos.

## Pruebas locales

```powershell
python -m unittest discover -s 01_patrones_agenticos\tests -v
```

Estas pruebas no llaman modelos ni necesitan GPU. Generan bases temporales y comprueban la referencia, límites del periodo, pedidos sin entrega, cancelaciones y rechazo de reemplazo de una base ajena.

## Consultas de solo lectura

[src/sql_readonly.py](src/sql_readonly.py) aplica los controles fuera del modelo: conexión SQLite de solo lectura, tablas y funciones permitidas, rechazo de escritura, máximo 25 filas y un segundo por consulta. Un error SQL se devuelve o comunica de forma explícita; no se cambia la consulta por una respuesta prefabricada.

Las pruebas verifican también la consulta de referencia, el truncamiento, el rechazo de acceso a metadatos y la cancelación por tiempo.

## Trazabilidad

Los eventos se guardan como JSONL dentro de `outputs\traces`. Las claves conocidas se ocultan antes de escribir o imprimir. Las utilidades de evaluación exigen todos los conteos y los tipos correctos, no solo que la respuesta contenga el número 11.
