# Caso 3: revisión de un expediente de compra

## Objetivos

1. Coordinar cinco subagentes con contratos Pydantic, montos `Decimal` y fechas `date`.
2. Separar relevancia de vigencia y mantener los controles deterministas antes del LLM.
3. Medir componentes y punta a punta sin confundir una propuesta con una aprobación.

Dirigido a profesionales con experiencia en Python e IA. Se necesitan Python 3.11,
el entorno común del repositorio y las dependencias del único
[requirements.txt](../requirements.txt). No se instala este tema como paquete.

## Recorrido

Comandos desde la raíz del repositorio. Sustituir `python` por el intérprete del
entorno común cuando no esté activado.

| Orden | Objetivo | Archivo y comando | Resultado esperado |
|---|---|---|---|
| 1 | Elegir una actividad | `python 07_caso3\src\main.py` | Menú numerado; solo ejecuta el script seleccionado en otro proceso |
| 2 | Observar tipos y vigencia sin modelo | `python 07_caso3\src\leccion_local.py` | Decimal, fecha ISO, manual sin filtro y circular vigente con filtro |
| 3 | Revisar un expediente real con el modelo | `python 07_caso3\src\run_case.py E01` | Cinco handoffs, dictamen propuesto e interrupción humana |
| 4 | Revisar y firmar en el mismo proceso | `python 07_caso3\src\run_case.py E01 --firmar` | Solicita identidad, rol y aceptar/rechazar después de mostrar la propuesta |
| 5 | Evaluar el sistema | `python 07_caso3\src\run_evals.py -k 3 --solo-agente e2e` | Tabla, CSV y una traza por intento en `outputs\evals` |
| 6 | Ejecutar controles CPU | `python 07_caso3\tests\run_cpu.py` | Contratos, corpus, RAG, SDK y compuerta humana sin red ni credenciales |

Para enviar una traza por intento y publicar las métricas de una evaluación en Langfuse, configurar
`LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` en el entorno o en `.env` y añadir
`--langfuse` al comando de evaluación. Para Langfuse Cloud, definir también
`LANGFUSE_BASE_URL` con la URL de la región del proyecto. El SDK requiere
Langfuse v4.59 o posterior. La traza incluye identificadores sintéticos y métricas,
no documentos, respuestas completas ni mensajes de error.

El menú conserva el código de salida del proceso seleccionado. Un fallo del
modelo, formato o control es un error visible, nunca una aprobación por defecto.

## Servicios, modelos y credenciales

Por defecto, la lección usa Groq mediante `ChatOpenAI` y el endpoint compatible
con OpenAI. También puede usar el servidor local de LM Studio con `gpt-oss-20b`.
Copiar [.env.example](.env.example) a `.env` en esta carpeta. Para LM Studio,
cargar el modelo e iniciar su servidor local en `http://127.0.0.1:1234/v1`, luego
configurar `CASO3_MODEL_PROVIDER=lm_studio`. El identificador predeterminado es
`openai/gpt-oss-20b`; `LM_STUDIO_MODEL` permite cambiarlo. Esta opción no requiere
clave real ni consume cuota externa. Para Groq, configurar `GROQ_API_KEY`.
No incluir claves en prompts, trazas ni archivos compartidos. Las variables del
proceso tienen prioridad sobre `.env`.

Las terminales anteriores que definen `MODEL_PROVIDER=local` conservan el
streaming y los ajustes `LOCAL_BASE_URL`, `LOCAL_MODEL`, `LOCAL_TIMEOUT` y
`LOCAL_REASONING_EFFORT`. Si ambos selectores están en la misma fuente,
prevalece `CASO3_MODEL_PROVIDER`. Un proveedor desconocido produce un error.

El modelo predeterminado es `openai/gpt-oss-20b`; `GROQ_MODEL` permite cambiarlo
para el orquestador. En la evaluación elegir explícitamente `--modelo`.
Ante un 429 por tokens por minuto, el cliente espera lo que indica Groq y
reintenta hasta ocho veces, con aviso en la consola. Una espera mayor de
90 segundos u otro error detiene la ejecución. Con el plan gratuito, una revisión
puede tardar varios minutos. Los comandos de revisión y evaluación consumen cuota. No hay un modo simulado
para estudiantes; los modelos falsos viven únicamente en las pruebas.

## Flujo y límites

El orquestador de Deep Agents planifica con `write_todos` y delega con `task`:
clasificador, extractor, verificador, auditor y redactor. Las salidas usan
[contratos compartidos](src/caso3/contratos.py) y el estado registra como máximo
dos vueltas hacia extractor o verificador. Una contradicción real entre documentos
se devuelve a una persona, no se reextrae indefinidamente.

El clasificador solo puede invocar `Clasificacion`. El extractor puede usar
`normalizar_monto` y `normalizar_fecha`, y debe entregar `Extracciones`. En ambas
etapas, escribir el JSON como texto no sustituye la llamada al contrato.
El verificador recibe solo `consultar_normativa` y `Reglas`. El auditor recibe
los cruces ya calculados y solo puede invocar `Hallazgos` para entregar su
revisión; una explicación en texto no la sustituye. Los cuatro usan las mismas
herramientas aislados y delegados, sin `write_todos` ni herramientas de archivos.
El orquestador conserva su planificación.

La recuperación local BM25 filtra la vigencia antes de ordenar. El manual de 2024
exige tres cotizaciones desde dos millones; la circular de 2026 baja ese umbral
a un millón. Ambos documentos son inventados. Los certificados tienen un máximo
de 90 días y deben conservar vigencia. Según la cuantía, firma el responsable de
compras o la dirección. El auditor expone el cálculo de ese firmante.

Los documentos son datos no confiables, nunca instrucciones. El orquestador no
puede ejecutar código ni operar sobre el sistema de archivos real; el backend
predeterminado es virtual. La lectura se confina al expediente con límites de
tamaño y páginas. Un PDF sin texto produce un bloqueo OCR explícito y escalamiento:
no se instala ni se activa un motor OCR automáticamente.

`proponer_aprobacion` se interrumpe con el mecanismo HITL nativo y
`InMemorySaver`. La propuesta se liga a un hash antes de la firma. La identidad
del revisor es declarada, no autenticada. Se comprueba que el rol declarado
corresponda a la cuantía: es una demostración educativa, no un
sistema de autorización de compras. El checkpoint vive solo en ese proceso.
Rechazar no ejecuta la herramienta de firma. La propuesta y su aceptación son
datos distintos; una decisión `escalar` no se convierte en `aprobar` por firmarla.

## Datos y evaluación

### Documentos del RAG

El corpus normativo está incluido en [data/corpus/normativa](data/corpus/normativa).
No hay que descargar documentos ni obtener acceso a un repositorio externo.

| Documento | Vigencia | Regla de cotizaciones |
|---|---|---|
| [Manual de compras 2024](data/corpus/normativa/manual-2024.md) | Del 1 de enero de 2024 al 31 de diciembre de 2025 | Tres desde $2.000.000 |
| [Circular de compras 2026](data/corpus/normativa/circular-2026.md) | Desde el 1 de enero de 2026, sin fecha final | Tres desde $1.000.000 |

Son documentos ficticios con metadatos de fuente, versión, vigencia, certificados
y firma. La circular sustituye al manual. El índice local se construye a partir
de estos archivos; no se versionan índices ni resultados generados.

### Expedientes y medición

Hay doce expedientes sintéticos: cuatro válidos, cinco con errores y tres trampas.
El golden incluye tipos, extracciones y hallazgos esperados. No se envía al flujo
E2E. En evaluación aislada se proporcionan los insumos dorados de etapas anteriores.

Las trampas son una instrucción oculta en PDF, una norma vieja citada en un anexo
y un NIT casi igual junto a una tabla escaneada. Para inspeccionar su rechazo sin
modelo, ejecutar las pruebas CPU. No equivale a medir resistencia de un LLM real.

```powershell
python 07_caso3\src\run_evals.py -k 3 --modelo openai/gpt-oss-20b --solo-agente e2e
python 07_caso3\src\run_evals.py -k 3 --modelo openai/gpt-oss-120b --solo-agente e2e
python 07_caso3\src\run_evals.py -k 3 --solo-agente extractor
python 07_caso3\src\run_evals.py -k 3 --solo-agente e2e --langfuse
```

Para probar E05 de punta a punta con el modelo local y ver la traza y el experimento:

```powershell
$env:CASO3_MODEL_PROVIDER = "lm_studio"
python 07_caso3\src\run_evals.py -k 1 --caso E05 --solo-agente e2e --langfuse --sesion-langfuse caso3-revision
```

Con `--langfuse`, cada intento E2E tiene una observación por etapa ejecutada:
`contrato_valido` indica si se validó la salida estructurada; `evidencia_fiel`
indica si el clasificador o el extractor conservó la evidencia, y
`control_superado` indica si se completó el traspaso. Un valor `null` no se
midió. Usa el mismo `--sesion-langfuse` antes y después de una corrección para
comparar las trazas. Se envían metadatos, no los documentos ni el texto del error.
Sin `--langfuse` el caso sigue funcionando sin exportar trazas.

`--solo-agente` admite clasificador, extractor, verificador, auditor, redactor y e2e.
`pass^k` exige que las k corridas de un expediente sean correctas. Un error cuenta
como fallo y produce salida no nula. Los falsos avances son propuestas de aprobar
cuando el golden pide otra decisión; su meta es cero, no un resultado asumido.
Las latencias se miden por intento. Los tokens E2E se suman desde el callback del SDK;
si un componente aislado no expone uso, el CSV deja el campo vacío, no pone cero.
Los nombres por fecha, modelo y componente y las trazas por expediente e intento
se sobrescriben al repetir la misma medición.

Los resultados comparativos 20b/120b y las trampas que atraviese cada modelo deben
medirse con esos comandos. No se incluyen cifras inventadas ni se presenta la
suite CPU como una corrida con Groq.

Las métricas aisladas del verificador y del redactor todavía no certifican
cobertura completa de reglas ni conservación íntegra de la evidencia. No usar
sus puntajes como aprobación. El flujo E2E aplica controles adicionales de
igualdad de reglas, hallazgos y dictamen antes de la interrupción humana.

## Trabajo en parejas

En [estudiante](src/estudiante/ejercicios.py) hay cuatro TODOs: normalizador,
vigencia, límite de vueltas y pass^k. No contiene sus soluciones.

| Ejercicio | Función que debe completar el estudiante | Criterio de aceptación |
|---|---|---|
| 1. Normalizar montos | `parse_amount` | Convertir `1.200.000` a `Decimal`, sin pasar por `float`, y rechazar entradas inválidas |
| 2. Filtrar normas | `filter_rules` | Usar la fecha del expediente, incluir los extremos y admitir vigencia final abierta |
| 3. Limitar revisiones | `request_revision` | Pasar de cero a una y de una a dos vueltas; rechazar una tercera |
| 4. Medir consistencia | `pass_power` | Exigir éxito en las primeras k corridas y fallar si falta alguna |

El flujo principal conserva sus controles implementados. Los ejercicios son
práctica separada: completarlos no sustituye automáticamente esos controles.
La comprobación de vigencia utiliza los mismos documentos normativos del RAG.

1. Una persona implementa los dos primeros; la otra completa contador y métrica.
2. Ejecutar `python 07_caso3\src\estudiante\comprobar.py`.
3. Al inicio deben verse cuatro errores `NotImplementedError`; no son pruebas aprobadas.
4. Intercambiar la revisión y añadir un borde a cada ejercicio.
5. Comparar un componente aislado con la revisión completa y explicar qué error se propaga.

## Puente a producción y material visual

En producción hacen falta autenticación y roles del firmante, checkpoints
durables, aprobaciones transaccionales y presupuestos de cuota. Las fuentes
normativas deben tener responsables y control de versiones.

Las [imágenes del recorrido](docs/evidencias/01_recorrido_general.png) y
[controles](docs/evidencias/02_controles_y_firma.png) describen el diseño. La
[lámina de estado](docs/evidencias/03_evaluacion_y_estado.png) conserva el estado
del momento en que se elaboró y no certifica una ejecución posterior.
