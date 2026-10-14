# Pruebas y aceptación

```powershell
python 05_caso2\tests\run_cpu.py --scaffold
python 05_caso2\tests\run_cpu.py
```

Andamiaje: API, límites y hash canónico. Contratos: identidad, evidencia, plan, roles y reconciliación. Esta rama resuelve los seis TODO y debe aprobar todos los contratos, sin convertir pruebas en skips.

## Validación incremental de E1

La deduplicación usa una transacción SQLite de escritura antes de consultar el ID.
Un evento nuevo devuelve `True`, uno idéntico devuelve `False` y un ID repetido
con otro contenido produce `ControlError` sin sobrescribir el original.
Las pruebas de `tests/test_events.py` comprueban persistencia y entregas concurrentes
con bases temporales. No requieren modelo ni servicios externos.

Desde la raíz del repositorio, en PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path 05_caso2\src).Path
python -m unittest discover -s 05_caso2\tests -p test_events.py -v
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k test_event_identity -v
```

Estas pruebas no validan los TODO restantes ni el recorrido completo.

## Validación incremental de E2

Cada campo requerido debe ser no vacío, coincidir exactamente con su evidencia
y aparecer literalmente en el cuerpo del correo. Esto no autentica al remitente
ni reemplaza la comprobación contra el registro de personal.

Con `PYTHONPATH` configurado como en E1:

```powershell
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k evidence -v
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k sender -v
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k injection -v
```

## Validación incremental de P1

El hash incluye todo el contenido del plan excepto la clave superior `hash`.
Reordenar claves no cambia el resultado; modificar acciones, versión u otro
contenido sí lo cambia. El cálculo no modifica el plan ni autoriza su ejecución.

Con `PYTHONPATH` configurado como en E1:

```powershell
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k plan_hash -v
```

## Matriz de aceptación

X1 reconcilia un cambio sin registro únicamente si `pending_action` identifica
la siguiente acción y el inventario coincide exactamente con su estado posterior.
Registra los hashes antes/después con `reconciled: true`, limpia el marcador y
persiste antes de continuar. Cualquier otro cambio invalida el plan y borra
aprobaciones, sin modificar el inventario.

```powershell
python -m unittest discover -s 05_caso2\tests -p test_execution.py -v
python 05_caso2\tests\run_cpu.py
```

P2 registra actor, rol, decisión, hash y versión, con la advertencia de identidad
declarada. Rechaza actor o rol repetido y decisiones de planes anteriores.
Un rechazo cierra el caso como `RECHAZADO`; dos aprobaciones no ejecutan Git.
P3 comprueba el hash recalculado, dos roles distintos y actores no vacíos
distintos, decisiones `approve` y hash y versión vigentes. Admite ejecución
inicial, reanudación parcial y repetición de un caso completado; bloquea casos
rechazados o invalidados. No autentica las identidades declaradas.

```powershell
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -k record_ -v
python -m unittest discover -s 05_caso2\tests -p test_graph.py -v
python -m unittest discover -s 05_caso2\tests -p test_contracts.py -v
```

| Escenario | Control | Esperado |
|---|---|---|
| Formulario válido | Evidencia y registro | Plan, sin escritura automática |
| Prosa irrelevante | intent | Rechazo |
| Prompt injection | intent/evidencia, permisos fuera del modelo | Sin ejecución |
| Remitente ajeno | Allowlist | Rechazo |
| Dato faltante o inventado | Contrato y fragmento literal | Rechazo |
| Identidad contradictoria | Registro sintético | Rechazo |
| Fecha futura | Reloj explícito | Bloqueo hasta fecha efectiva |
| Mismo ID, mismo contenido | Diario de eventos | Duplicado |
| Mismo ID, otro contenido | Hash del evento | Conflicto |
| Otra entrega, misma solicitud | Registro de casos | No prepara otra baja |
| Falta un rol | Autorización completa | Sin cambios |
| Actor o rol repetido | Separación declarada | Rechazo |
| Aprobación vieja | Hash y versión | Rechazo |
| Plan manipulado | Hash recomputado | Rechazo |
| Visibilidad incompleta | Inventario complete | Desconocido, no ausencia |
| Inventario cambiado | Comparación completa | Invalidar y replanificar |
| Fallo parcial | Diario y verificación | Reporte parcial, reanudación |
| Cambio sin registro | pending y estado esperado | Reconciliar sin repetir |
| Propietario único | Advertencia manual | Cierre no afirma finalización total |
| Pausa/reinicio | SQLite LangGraph | Conservar aprobación y segunda pausa |
| Error de tracking | Excepción visible | No éxito silencioso |

Los dobles de extracción, si se usan, quedan solo en pruebas. Las pruebas CPU no certifican que el modelo detecte una injection: comprueban que su salida no se convierte en autoridad. El smoke real evalúa extracción contra etiquetas, no con un juez LLM.

## Integración opcional

Después de autorización y preparación:

```powershell
$env:RUN_MODEL_INTEGRATION = "1"
python 05_caso2\tests\integration\smoke_model.py
```

Requiere también ALLOW_MODEL_CALLS y credenciales o modelo local. Consume una llamada real y no modifica Git. Si no se autorizó, reportar "integración pendiente".

Ejecutar temas del curso en procesos independientes para evitar colisiones de módulos. CI remoto no se presume ejecutado por pruebas locales.
