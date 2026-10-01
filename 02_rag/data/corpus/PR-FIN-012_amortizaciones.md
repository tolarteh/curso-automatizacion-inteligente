---
titulo: Procedimiento de solicitudes de amortización
codigo: PR-FIN-012
clasificacion: interna
origen: interno
version: 3.1
fecha: 2026-05-12
---

Documento sintético del centro Aurora. Las reglas solo aplican al laboratorio.

## 1. Objeto y alcance

Define cómo recibir, validar y pagar una solicitud de amortización de anticipos para proyectos de investigación. Aplica a solicitudes radicadas desde el 1 de junio de 2026; las anteriores usan la versión 2.4.

## 2. Soportes obligatorios

La solicitud llega en un único ZIP con estos soportes:

- DEM-AMZ-03: solicitud firmada por el director del proyecto.
- DEM-AMZ-05: certificación bancaria con expedición no mayor a 30 días.
- DEM-AMZ-07: conciliación de pagos parciales, exigida cuando hay más de un desembolso.
- Factura electrónica o cuenta de cobro.

Si falta un soporte obligatorio, se devuelve al solicitante dentro de los 3 días hábiles siguientes a la radicación, indicando qué documento falta.

## 3. Validación cruzada de montos

Se compara el monto solicitado en DEM-AMZ-03 con la suma de los pagos realizados según los comprobantes. La diferencia absoluta no puede superar el 0,5 % del monto solicitado ni 200.000 pesos; se aplica el menor límite.

Si supera la tolerancia, la solicitud queda EN REVISIÓN. El Grupo de Control Financiero tiene 5 días hábiles para pronunciarse. El analista no puede aprobarla en ese estado.

## 4. Plazos de pago

Una solicitud aprobada se paga dentro de los 15 días hábiles siguientes a la fecha de aprobación. El plazo se suspende mientras esté EN REVISIÓN. Los pagos se programan los martes y jueves.

## 5. Documento resumen trazable

El resumen lista cada soporte y su huella SHA-256, monto solicitado, suma pagada, diferencia y decisión con el nombre del responsable. Se archiva junto al ZIP durante 10 años.
