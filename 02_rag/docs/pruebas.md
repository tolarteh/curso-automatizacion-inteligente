# Pruebas de RAG

## CPU y CI

Desde la raíz, con el entorno común:

```powershell
python 01_patrones_agenticos\tests\run_cpu.py
python 02_rag\tests\run_cpu.py
python -m pip check
```

GitHub Actions ejecuta ambos runners en procesos separados, en Windows y Linux. Cada runner bloquea conexiones y DNS durante descubrimiento y ejecución. Instalar las dependencias sí requiere red.

Los dobles solo viven en pruebas. Se comprueban metadatos, etiquetas, ventanas, cuarentena del documento completo, permisos antes del ranking, normalización, caché, códigos exactos y fusión RRF.

Las pruebas del grafo provocan abstención, citas inválidas, juicios contradictorios y agotamiento de las dos generaciones. Verifican que el texto bloqueado no se publique como respuesta final y que la inspección del grafo no cree clientes de modelos.

Las métricas se contrastan con un cálculo manual; las pruebas del evaluador cubren denominadores, alternativas de claves y límites numéricos. Esto no demuestra calidad de un modelo real.

## Integración local explícita

Con LM Studio preparado y los dos modelos configurados:

```powershell
python 02_rag\tests\integration\smoke_local.py --run
```

El flag autoriza inferencia real. No se inicia un servidor, descarga un modelo ni cambia a un proveedor remoto. LM Studio puede cargar un modelo disponible al recibir la solicitud.

Se prueban siete escenarios: básico, avanzado, pregunta reservada como analista, la misma como seguridad, plazo de pago ante el correo en cuarentena, evaluación A a D y evaluación con reescritura E.

Cada ejecución debe terminar correctamente y crear una traza nueva. Se exige evidencia de embeddings reales, uso del modelo de lenguaje según el modo, claves esperadas, topes del grafo y cero fuentes no permitidas en las configuraciones protegidas.

Un fallo detiene la prueba. El informe completo o parcial queda en `outputs\integration_result.json`, fuera de Git. No hay reintentos del smoke ni respaldo remoto. Los reintentos semánticos del grafo sí son parte visible del laboratorio y tienen topes.

Esta integración no corre en CI ni certifica uso físico de GPU. Tampoco garantiza resultados idénticos en futuras respuestas del modelo.

Los checkers de ejecución comprueban errores y asserts, no calidad semántica. El estado `verificada` comprueba citas y sustentación mediante un juez de modelo; no demuestra que la respuesta cubra todo lo preguntado. El juez de relevancia puede seleccionar un fragmento de alcance y omitir las acciones pedidas.
