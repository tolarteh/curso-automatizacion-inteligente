# Entrega del reto

## Núcleo obligatorio

Completar los mismos archivos de `src`; no cambiar los contratos de pruebas.

| TODO | Archivo | Pista inicial | Evidencia |
|---|---|---|---|
| E1 | events.py | SELECT e INSERT dentro de una transacción; comparar digest | Repetición no crea otra entrega; contenido diferente falla |
| E2 | extraction.py | Valor y fragmento deben coincidir literalmente en body | Campo inventado no avanza |
| P1 | planning.py | Orden canónico; excluir únicamente hash | Cambiar acción o versión cambia hash |
| P2 | planning.py | Revisar roles y actores antes de añadir evidencia | Rol repetido o mismo actor falla |
| P3 | planning.py | Verificar cada aprobación, no solo la longitud | Versión vieja no ejecuta |

Tiempo principal para E2, P1, P2 y P3. E1 es una discusión de identidad de eventos, no una implementación de Graph.

## Extensión opcional

X1 en `execution.py`: reconciliar corte entre cambio y diario. Solo aceptar exactamente la transición de la siguiente acción marcada pending. Cualquier otro estado invalida plan y limpia aprobaciones. El andamiaje ya conserva diario y genera cierre parcial.

## Qué entregar

- Pruebas CPU y explicación de cada rechazo, incluido qué control lo produjo.
- Plan visible con advertencias, dos aprobaciones y reporte comprobado.
- Fallo parcial y reanudación, distinguiendo pendiente manual de error automático.
- Justificación de formulario, prosa libre o solución híbrida.
- Comparación contra etiquetas de extracción si hay inferencia autorizada; de lo contrario declarar pendiente, no inventar métricas.
- Tres capturas o notas del visor MLflow: política rechazada, inventario cambiado y fallo parcial. No incluir credenciales ni cuerpos no sintéticos.

La solución conserva los mismos contratos. No aceptar borrar pruebas, simular respuestas del modelo para estudiantes ni devolver éxito ante excepción.
