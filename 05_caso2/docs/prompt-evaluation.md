# Comparación pequeña de prompts

El experimento compara cinco instrucciones de extracción sobre doce correos
sintéticos etiquetados. Sigue el ciclo de registro, evaluación y comparación del
[artículo de MLflow](https://mlflow.org/blog/mlflow-prompt-optimization/), pero
no usa GEPA, generación automática de prompts ni un juez LLM. No requiere paquetes nuevos.

## Ejecutar

Desde la raíz del repositorio, con MLflow local arrancado y credenciales configuradas:

```powershell
conda activate agentes
$env:ALLOW_MODEL_CALLS = "1"
$env:SYNTHETIC_TRACES = "1"
python 05_caso2\src\evaluate_prompts.py --provider groq
```

Máximo 60 llamadas, sin reintentos. Con este corpus son 55: el remitente ajeno
se bloquea antes de llamar al modelo, una vez por candidato. El experimento
espacia el inicio de llamadas al menos diez segundos para reducir saturación;
esto no garantiza disponibilidad ni evita todas las cuotas del proveedor.
La espera queda fuera de la latencia de ingesta. No reintenta errores 429.
Si hay errores de configuración, transporte o proveedor, etiqueta la comparación como `comparable=false`
y el candidato como `evaluation_status=incomplete`; no elegir ganador.
El experimento
usa el modelo de `GROQ_MODEL`; con `--provider local`, usa `LOCAL_MODEL`.
No deduplica, no requiere la API de correo y no crea casos, planes persistidos,
aprobaciones ni cambios en Git. No modifica el prompt operativo `extract.txt`.

## Qué cambia y qué queda fijo

`prompts/candidates.json` define baseline, checklist, ejemplos, fronteras de
responsabilidad y una versión concisa. Las primeras cuatro reutilizan
`extract.txt`; la última reemplaza la instrucción completa.
Los cinco prompts completos se registran como versiones de `case2-extraction`.
Cada run carga su versión exacta, no un alias que pueda cambiar.

`data/prompt_eval.json` contiene correos, etiquetas y registro de personal propios.
Incluye distractores, citas, datos en distinto orden, fecha relativa, fecha futura,
identidad contradictoria con el registro, múltiples bajas e instrucciones de
omitir controles. Los seis correos del ejercicio original no se modifican.

Proveedor, modelo, temperatura, límites y corpus se mantienen constantes.
La política es la misma del laboratorio. El modelo debe extraer una fecha ISO
futura o identidad escrita; el código decide si pueden avanzar.

## Leer MLflow

Abrir `case2-prompt-evaluation` en http://127.0.0.1:5005.
El run `five-prompts` agrupa cinco runs hijos. Comparar las métricas de los hijos
y abrir sus artifacts para revisar prompt completo, etiquetas, salidas y errores.
La pestaña Prompts muestra las versiones; `prompt_uri` y `prompt_hash` identifican
la instrucción utilizada. Traces contiene `evaluate_ingestion` y la llamada
LangChain, con datos sintéticos de entrada y salida.

Los resultados locales quedan en `outputs/prompt-evaluation/<batch_run_id>`.
Cada ejecución conserva su directorio; no reemplaza evaluaciones anteriores.

| Métrica | Cálculo |
|---|---|
| extraction_exact | Intent y los cuatro campos idénticos a la etiqueta, sobre 11 intentos de extracción |
| intent_accuracy | Clasificación correcta, sobre 11 intentos |
| accuracy_* | Exactitud por campo, incluye vacíos esperados |
| json_valid_rate | Respuestas que pasan el esquema Pydantic, sobre 11 intentos |
| policy_accuracy | Aceptaciones/rechazos correctos sobre los 12 correos; error técnico no cuenta como rechazo correcto |
| valid_accept_rate | Casos válidos que avanzan, sobre los 4 válidos |
| false_accept_count/rate | Casos negativos que avanzan, sobre los 8 negativos |
| errors | Total de fallos de extracción/API, separados de rechazos de política |
| model_output_errors | Respuestas del modelo fuera del contrato JSON; cuentan como fallo de calidad |
| operational_errors | Configuración, transporte o proveedor; impiden comparar calidad sin sesgo |
| tokens_known | Tokens reportados por respuestas válidas; no estima los de llamadas fallidas |
| usage_unknown_calls | Intentos sin métricas de uso disponibles |
| ingestion_latency_ms_mean | Tiempo de extracción y política, incluye controles sin modelo; excluye transporte y persistencia |

## Elegir una variante

Primero revisar falsas aceptaciones y errores. Luego comparar extracción exacta
y aceptación de los casos válidos; tokens y latencia ayudan a desempatar.
Inspeccionar los errores concretos antes de concluir que un prompt mejora.
FINISHED significa que la comparación terminó, no que todos los correos pasaron.

Este corpus es de desarrollo: una ejecución por correo no mide estabilidad ni
generalización. No es un benchmark institucional ni una prueba exhaustiva contra
prompt injection. Separar un corpus nuevo antes de promover un ganador.
El script no promueve ninguna versión automáticamente.

## Primera comparación ejecutada

Se ejecutó con Groq, modelo `openai/gpt-oss-20b`, el 14 de octubre de 2026.
El primer batch sufrió errores 429 de cuota y está marcado como no comparable.
El segundo batch, con llamadas espaciadas, no tuvo errores de proveedor:

| Candidato | Extracción exacta | Falsas aceptaciones | Salidas fuera del esquema |
|---|---|---|---|
| baseline | 10/11 | 0/8 | 1 |
| checklist | 9/11 | 1/8 | 0 |
| examples | 8/11 | 2/8 | 0 |
| boundaries | 9/11 | 1/8 | 1 |
| concise | 10/11 | 0/8 | 1 |

El baseline y la variante concisa empataron en esos criterios.
Los ejemplos no mejoraron esta ejecución: dejaron avanzar la injection y el
correo de múltiples personas. La checklist dejó avanzar el de múltiples personas.
Las fronteras dejaron avanzar la injection y fallaron el esquema en un correo válido.
Avanzar significa superar extracción y política en esta evaluación, no ejecutar
una baja: no se construyen casos ni se solicitan aprobaciones.

La evidencia literal no detecta por sí sola instrucciones maliciosas cuando
los campos también están presentes. El experimento muestra ese límite,
sin afirmar que una variante lo resuelva en general.
Se conserva el prompt operativo; no hay evidencia para promover una mejora.
