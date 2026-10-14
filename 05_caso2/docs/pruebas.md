# Pruebas y aceptación

```powershell
python 05_caso2\tests\run_cpu.py --scaffold
python 05_caso2\tests\run_cpu.py
```

Andamiaje: API, límites y hash canónico. Contratos: TODO de identidad, evidencia, plan, roles y reconciliación. El reto incompleto falla explícitamente; no convertir esas pruebas en skips. La solución debe aprobar todos los contratos.

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

Para contrastar las cuatro etiquetas y recorrer formulario y prosa con dos aprobaciones, ejecución simulada, cierre y trazas reales:

```powershell
$env:RUN_MODEL_INTEGRATION = "1"
$env:ALLOW_MODEL_CALLS = "1"
$env:SYNTHETIC_TRACES = "1"
$env:PYTHONUTF8 = "1"
python 05_caso2\tests\integration\validate_real.py --provider groq
python 05_caso2\tests\integration\validate_real.py --provider local
```

Arrancar antes API y MLflow según preparación. Cada ejecución conserva evidencia en una carpeta nueva de `outputs\integration`, sin borrar los casos previos. El script verifica que aprobar no cambia inventario, bloquea ejecución sin aprobación, compara evidencia literal y exige trazas enlazadas a runs del caso. Una respuesta no JSON o una etiqueta incorrecta no cuenta como extracción exacta, aunque el rechazo impida ejecutar. No sustituye ni descarga modelos. UTF-8 evita errores de consola con los enlaces que imprime MLflow en Windows.

Ejecutar temas del curso en procesos independientes para evitar colisiones de módulos. CI remoto no se presume ejecutado por pruebas locales.
