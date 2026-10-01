---
titulo: Diccionario de datos de proyectos
codigo: DD-BD-001
clasificacion: interna
origen: interno
version: 2.0
fecha: 2026-04-20
---

Documento sintético del centro Aurora.

## 1. Tabla proyectos

Hay una fila por proyecto de investigación. Columnas: id_proyecto, nombre, id_linea, fecha_inicio, fecha_fin_prevista y estado.

Estados: A activo, S suspendido y C cerrado. Los proyectos vigentes incluyen A y S; los suspendidos siguen vigentes para efectos presupuestales.

## 2. Tabla contratos

Hay una fila por contrato. La vigencia es el año fiscal en que se firmó el contrato, no su año de ejecución. valor_total está en pesos colombianos sin decimales.

## 3. Tabla desembolsos

Un contrato puede tener varios desembolsos. Para obtener lo pagado se suman las filas con anulado igual a 0. Las anuladas se conservan por auditoría.

## 4. Reglas de consulta

El usuario del asistente es de solo lectura y solo ve proyectos, contratos y desembolsos. El límite es de 200 filas; el corte es el último día hábil del mes anterior.
