# Recuperación aumentada por generación

## Recorrido

| Lección | Objetivo | Comando desde la raíz | Qué observar |
|---|---|---|---|
| [RAG básico](src/01_rag_basico.py) | Separar indexación, recuperación y generación | `python 02_rag\src\01_rag_basico.py` | Respuesta sin contexto, fragmentos recuperados y respuesta con citas |
| [RAG avanzado](src/02_rag_avanzado.py) | Aplicar permisos, relevancia, verificación y topes | `python 02_rag\src\02_rag_avanzado.py` | Recorrido del grafo, contexto permitido y cierre verificado, abstención o bloqueo |

El básico omite permisos y cuarentena para mostrar sus limitaciones. Solo admite modelo local y datos sintéticos. Sus indicadores de citas no verifican fidelidad. Usar `--fragmentacion secciones` para comparar con ventanas fijas, `--sin-comparar` para omitir la primera respuesta y `--reindexar` para regenerar vectores.

El avanzado admite `--pregunta`, `--rol analista|seguridad` y `--k`. `--grafo` imprime Mermaid sin llamadas a modelos. Con `--backend groq`, la recuperación excluye también la información reservada aunque se seleccione el rol de seguridad. Un bloqueo termina con código 2, no con una respuesta no verificada.

## Datos disponibles

El [corpus](data/corpus) contiene documentos sintéticos del centro Aurora. Sus reglas y códigos son ficticios y solo sirven para el laboratorio.

- [Amortizaciones](data/corpus/PR-FIN-012_amortizaciones.md): soportes, tolerancias y plazos.
- [Catálogo de formatos](data/corpus/CT-FIN-003_catalogo_formatos.md): códigos parecidos con responsables distintos.
- [Desvinculación de cuentas](data/corpus/PR-TIC-004_desvinculacion_git.md): pasos, aprobaciones y plazos.

Los documentos consumidos por la recuperación viven en `data\corpus`, separados de la documentación para estudiantes.

El corpus tiene ocho documentos. Incluye reglas de uso de IA, diccionario de proyectos, preguntas frecuentes, un acta marcada como reservada y un correo externo con una instrucción maliciosa. El correo es una entrada no confiable, no una regla del laboratorio.

El [conjunto de evaluación](data/evaluacion/preguntas.json) tiene 15 preguntas, con rol, evidencia esperada, claves de respuesta y datos prohibidos. Dos preguntas deben provocar abstención.

## Pruebas CPU

Desde la raíz del repositorio y con el entorno común:

```powershell
python 02_rag\tests\run_cpu.py
```

El runner bloquea conexiones y DNS. Comprueba metadatos, permisos de las etiquetas de evaluación y consistencia entre preguntas y corpus, sin llamar a modelos.

## Fragmentación y permisos

[La fragmentación](src/chunking.py) permite comparar ventanas de 400 caracteres con fragmentos por sección de hasta 900 caracteres. Los encabezados conservan título, código y sección.

[La política](src/policy.py) permite al analista consultar información pública e interna; el rol de seguridad también ve la reservada, pero esta nunca puede enviarse a un modelo externo. Los roles son una simplificación del laboratorio, no autenticación.

La cuarentena busca patrones de instrucciones dentro del documento completo y transmite la marca a todos sus fragmentos. Así, partir el texto no elimina la marca. Es una heurística: no detecta todas las inyecciones y puede producir falsos positivos.

## Configuración

Copiar [.env.example](.env.example) a `.env` en la raíz del tema. Las variables del proceso tienen prioridad. Los endpoints locales solo aceptan loopback; no se cambia de proveedor ante un error.

LM Studio y sus modelos se preparan aparte del entorno Python. El modelo de lenguaje usa el identificador `demo-local`; los embeddings usan `text-embedding-nomic-embed-text-v1.5`. Nomic requiere prefijos distintos para documentos y preguntas, definidos en el ejemplo de configuración.

Groq requiere clave y salida a internet, y solo se usa si se selecciona explícitamente. Los embeddings siempre son locales. Las trazas JSONL se guardan en `outputs\traces`, fuera de Git, con ocultamiento de claves conocidas.

Instalar o actualizar el entorno común con el `requirements.txt` raíz. NumPy calcula normas y similitudes; el SDK de OpenAI llama al servidor compatible. El cliente de embeddings verifica cantidad, orden, dimensiones y valores finitos, y rechaza vectores nulos.

## Índice local

[El índice](src/retrieval.py) guarda vectores en `outputs\indices`. La clave incluye el contenido del corpus, fragmentación, endpoint, modelo y prefijos. Los metadatos de permisos siempre se reconstruyen desde los documentos, no desde la caché.

Una caché dañada produce un error; no se recalcula silenciosamente. La opción `force=True` de `Index.build` regenera explícitamente los vectores. Cambiar los pesos detrás del mismo identificador de modelo requiere esa regeneración: el nombre no identifica por sí solo sus pesos.

[La recuperación híbrida](src/hybrid.py) combina similitud coseno y BM25. La fusión RRF suma `1 / (60 + posición)` por buscador; no mezcla directamente sus puntajes. La búsqueda léxica conserva códigos completos como `DEM-AMZ-09`. Los permisos y la cuarentena se aplican antes de ordenar resultados en ambos buscadores.

## Grafo acotado

[El grafo LangGraph](src/rag_graph.py) reescribe, recupera, califica, genera y verifica. Puede intentar dos búsquedas y dos generaciones como máximo. Si no encuentra evidencia, se abstiene. Si la respuesta sigue sin verificar, la bloquea en lugar de publicarla como respuesta final.

Las citas se comprueban en código; el juicio de fidelidad del modelo también puede equivocarse. LangGraph es una dependencia del entorno común. La telemetría externa de LangSmith y LangChain debe estar desactivada; habilitarla produce un error antes de ejecutar el grafo.
