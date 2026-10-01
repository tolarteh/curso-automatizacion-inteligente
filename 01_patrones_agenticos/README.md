# Patrones agénticos

## Datos y referencia

El ejemplo usa 26 pedidos sintéticos de cinco regiones. El informe incluye pedidos con fecha prometida en marzo de 2026, al corte del 5 de abril.

Un pedido está retrasado si se entregó después de la fecha prometida o sigue sin entregar al corte. Se excluyen los cancelados. El resultado esperado es 11 retrasados: Cundinamarca 5, Antioquia 3, Valle del Cauca 2 y Atlántico 1.

La referencia está en [data/fixtures/expected.json](data/fixtures/expected.json). El generador calcula el mismo resultado en Python, sin SQL ni modelo.

## Preparación

Usar el entorno común explicado en el [README raíz](../README.md). Desde la raíz del repositorio:

```powershell
python 01_patrones_agenticos\src\seed.py
```

La base se guarda en `outputs`, ignorado por Git. Si ya existe, el comando no la sobrescribe. `--reset` solo reemplaza una base que conserve el marcador de datos sintéticos.

## Pruebas locales

```powershell
python -m unittest discover -s 01_patrones_agenticos\tests -v
```

Estas pruebas no llaman modelos ni necesitan GPU. Generan bases temporales y comprueban la referencia, límites del periodo, pedidos sin entrega, cancelaciones y rechazo de reemplazo de una base ajena.

## Consultas de solo lectura

[src/sql_readonly.py](src/sql_readonly.py) aplica los controles fuera del modelo: conexión SQLite de solo lectura, tablas y funciones permitidas, rechazo de escritura, máximo 25 filas y un segundo por consulta. Un error SQL se devuelve o comunica de forma explícita; no se cambia la consulta por una respuesta prefabricada.

Las pruebas verifican también la consulta de referencia, el truncamiento, el rechazo de acceso a metadatos y la cancelación por tiempo.
