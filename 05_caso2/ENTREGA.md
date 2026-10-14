# Entrega de la pareja · Caso 2: baja en Git desde un correo

**La pregunta de hoy:** el agente dice "cuenta bloqueada", pero la cuenta sigue activa. ¿Qué controles impiden que eso pase y cómo lo demuestran?

Una copia por pareja. Llénenla **durante** la clase: al cerrar cada bloque, dediquen entre 3 y 5 minutos a su sección.

**Cómo trabajar:** una persona escribe el código y la otra revisa y pregunta. **Cambien de rol en cada TODO.** Al final, los dos deben poder explicar cualquier control sin leerlo.
**En la mesa:** en cada puesta en común, ataquen los controles de la otra pareja (hash viejo, mismo actor, correo duplicado) y anoten el resultado en la sección 2.
Escriban frases cortas y con sus palabras. Si algo no lo lograron, escriban "pendiente" y por qué; eso también vale.

**Cómo entregar:** guárdenla como `05_caso2/entregas/pareja-N.md` y súbanla con su rama o PR (o péguenla en el formulario del profe).

---

## 0. Datos de la pareja

| Campo | Respuesta |
|---|---|
| Pareja (número) e integrantes | |
| `python 05_caso2\tests\run_cpu.py`: ¿cuántos contratos quedaron pendientes? | |
| `case_id` con el que trabajaron | |
| `plan_hash` aprobado (primeros 12 caracteres) | |
| ¿Hubo inferencia autorizada con un modelo? (sí / no) | |

## 1. Qué tienen que resolver

**Mínimo para todas las parejas:** E2, P1 y P3. **Si les sobra tiempo:** E1 y P2. **Extra:** X1.

| TODO | Archivo | Qué debe pasar | ✔ |
|---|---|---|---|
| E2 | `extraction.py` | Un dato que no aparece literal en el correo **no avanza** | |
| P1 | `planning.py` | Si cambian una acción o la versión, **cambia el hash** | |
| P3 | `planning.py` | Una aprobación vieja o incompleta **no ejecuta** | |
| E1 | `events.py` | El mismo correo dos veces crea **una sola** entrega; mismo ID con contenido distinto **falla** | |
| P2 | `planning.py` | El mismo rol dos veces o el mismo actor en ambos roles **falla** | |
| X1 | `execution.py` | Tras un corte, solo se reanuda la acción `pending` que sigue; cualquier otra cosa invalida el plan | |

Reglas: no borren pruebas, no las conviertan en skip y no devuelvan éxito ante una excepción.

## 2. Cada control, en una frase

Por cada TODO que resolvieron, digan qué ataque o error frena.

| TODO | ¿Quién escribió y quién revisó? | ¿Qué rechaza? (ejemplo concreto) | ¿Lo resistió cuando la otra pareja lo atacó? |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

## 3. El recorrido completo

Peguen la salida resumida de cada paso (sin credenciales):

1. **Validación** (`01_eventos_y_validacion.py`): ¿qué datos se extrajeron y qué advertencias salieron?
2. **Plan y dos firmas** (`02_plan_y_aprobacion.py`): ¿qué roles aprobaron y con qué hash y versión?
3. **Un rechazo**: ¿qué intentaron (hash viejo, mismo actor, rol repetido) y qué mensaje salió?
4. **Ejecución y cierre** (`03_ejecucion_y_cierre.py`): ¿qué dice `report.md`? ¿Qué quedó pendiente de forma manual?

```
(peguen aquí)
```

## 4. Fallo parcial

Corran con `--fail-after` o `--crash-after-change`.

- ¿Qué acciones quedaron hechas y cuáles pendientes?
  >
- ¿Cómo distingue el reporte un **pendiente manual** de un **error automático**?
  >
- ¿El mensaje de `notification.txt` dice la verdad sobre el estado de la cuenta?
  >

## 5. MLflow: tres evidencias

Abran http://127.0.0.1:5005 (experimento `synthetic-offboarding`) y anoten el run y lo que vieron:

| Situación | Run | ¿Qué muestra MLflow? |
|---|---|---|
| Política rechazada | | |
| Inventario cambiado después de aprobar | | |
| Fallo parcial | | |

## 6. ¿Agente, flujo tradicional o híbrido? (obligatorio)

Completen la tabla **a medida que avanzan**, no al final.

| Paso | ¿Necesita un LLM? (sí / no) | ¿Por qué? | Costo o riesgo si lo usa |
|---|---|---|---|
| Recibir el correo y deduplicarlo | | | |
| Extraer los datos | | | |
| Armar el plan | | | |
| Aprobar | | | |
| Ejecutar en Git | | | |
| Notificar | | | |

**Nuestra recomendación** (formulario, prosa libre o híbrido) y por qué, en 3 o 4 líneas:

>

Si no hubo inferencia autorizada, escriban "métricas de extracción: pendiente". **No inventen números.**

## 7. Reglas para la guía de seguridad

Dos o tres reglas con el formato *"Cuando [situación], el sistema debe [regla], porque [riesgo que evita]."*

1.
2.
3.

¿Qué regla quedó en el **código** y no en el prompt? ¿Por qué?

>

## 8. Autoevaluación individual (cada uno responde por su cuenta)

Copien las preguntas una vez por integrante, con su nombre al inicio.

1. ¿En qué paso un LLM aporta algo que un formulario no da?
   >
2. Si el agente dice "completado", ¿qué revisarían para creerle?
   >
3. ¿Qué protege el hash del plan que no protegen las dos firmas por sí solas?
   >
4. ¿Qué no se puede probar hoy sin la plataforma real ni TI?
   >
5. Una duda que nos llevamos:
   >
