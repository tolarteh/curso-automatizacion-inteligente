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
