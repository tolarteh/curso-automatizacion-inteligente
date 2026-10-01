# Recuperación aumentada por generación

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
