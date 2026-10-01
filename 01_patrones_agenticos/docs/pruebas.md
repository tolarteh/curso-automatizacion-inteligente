# Pruebas sin modelo

Desde la raíz del repositorio, con el entorno común activo:

```powershell
python 01_patrones_agenticos\tests\run_cpu.py
```

El mismo runner se usa en GitHub Actions. Bloquea conexiones y resolución de nombres durante el descubrimiento y la ejecución: una prueba que intente llamar a un modelo o servicio falla.

Los dobles de modelo viven en `tests`, nunca en las lecciones. Sirven para provocar resultados incorrectos, respuestas inválidas, errores consecutivos y planes sin autorización de manera repetible.

## Qué se comprueba

- Datos sintéticos y referencia independiente de 11 retrasados.
- Permisos SQL, truncamiento y límites de tiempo.
- Tipos y campos de los contratos de herramientas y planes.
- Conteos exactos, incluso cuando el crítico afirma que un resultado incorrecto cumple.
- Límites de rondas, llamadas, turnos y errores.
- Revisión humana antes de pasos de riesgo alto.
- Rechazo sin entrada de la persona y ausencia de envíos.
- Ocultamiento de claves en trazas y pantalla.
- Selección del menú, rutas y propagación del código de salida.
- Prioridad de configuración y ausencia de cambio automático de proveedor.

## GitHub Actions

El workflow corre en cada PR dirigido a `main` y cada push a `main`, además de permitir ejecución manual. Usa Python 3.11 en runners de GitHub con Windows y Linux, instala el manifest raíz y ejecuta `pip check` antes de probar.

No usa claves, GPU, LM Studio ni un runner conectado al equipo del docente. El token del workflow tiene permiso de lectura del contenido; las acciones están fijadas por commit.

El paso de instalación sí requiere red para descargar paquetes. La prohibición de red se aplica a la ejecución de las pruebas.

Estas pruebas no miden calidad del modelo real ni demuestran que la GPU esté disponible. Un modelo puede producir un SQL o un plan incorrecto aunque las pruebas de los controles pasen.

La configuración sigue la [guía de pruebas Python de GitHub Actions](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).

## Integración con el modelo local real

Con LM Studio activo, un modelo compatible identificado como `demo-local` y el entorno común:

```powershell
python 01_patrones_agenticos\tests\integration\smoke_local.py --run
```

El flag autoriza las llamadas locales y la regeneración de la base sintética. No se inicia el servidor, no se carga un modelo y no se usa Groq como alternativa.

Se ejecutan Reflection, Tool use, el caso de rechazo de escritura y Planning con rechazo humano explícito. Cada ejecución debe devolver código 0 y generar una traza nueva con respuesta del modelo y criterios de comprobación específicos.

Los casos corren secuencialmente. Un fallo detiene la prueba, sin reintentos ni cambio de proveedor. El informe, incluidas las comprobaciones parciales si falla, queda en `outputs\integration_result.json`, fuera de Git.

Esta prueba no corre en GitHub Actions y puede fallar por disponibilidad o por una respuesta incorrecta del modelo. No basta con que el endpoint responda. Tampoco demuestra que la inferencia haya usado GPU: eso se observa en LM Studio.
