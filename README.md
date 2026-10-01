# Curso de automatización inteligente

Código del curso para construir agentes y soluciones de automatización con Python. Las lecciones usarán datos sintéticos y modelos reales.

## Estado del repositorio

El repositorio incluye datos sintéticos y pruebas para los temas publicados. Las dependencias se incorporan junto al código que las necesita.

## Temas

| Tema | Contenido disponible |
|---|---|
| [Patrones agénticos](01_patrones_agenticos/README.md) | Reflection con modelo real y verificación independiente |

## Entorno compartido

Se usará Python 3.11 y un solo entorno para todo el repositorio. Elegir venv o conda, no crear un entorno distinto por tema.

Los comandos siguientes se ejecutan desde la raíz del repositorio.

### Opción venv

En PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

Si el sistema bloquea la activación, se puede usar el intérprete del entorno directamente, sin cambiar la política de ejecución:

```powershell
.\.venv\Scripts\python.exe --version
```

### Opción conda

Desde una terminal con conda inicializado, por ejemplo Anaconda Prompt:

```text
conda create -n automatizacion-inteligente python=3.11
conda activate automatizacion-inteligente
python --version
```

### Dependencias

El único manifest es [requirements.txt](requirements.txt), ubicado en la raíz. Contiene las dependencias de los temas publicados; los paquetes se añaden junto al código que los utiliza.

Cuando se publique código con dependencias, instalarlas o actualizar el mismo entorno:

```powershell
python -m pip install -r requirements.txt
python -m pip check
```

Si se usa venv sin activación, sustituir `python` por `.\.venv\Scripts\python.exe`.

Las aplicaciones externas, servicios y modelos no se instalan con pip. Cada tema documentará los que necesita.

## Organización de cada tema

Cada tema seguirá esta estructura, creando solo las carpetas que necesite:

```text
<tema>\
  README.md
  .env.example
  src\
    main.py
    <lecciones y soporte Python>
  tests\
  prompts\
  docs\
    arquitectura.html
    arquitectura.json
  data\
    <entradas sintéticas y referencias>
  outputs\                 (local, ignorado)
```

- `src`: lecciones ejecutables y soporte mínimo. No requiere instalar el tema como paquete.
- `tests`: pruebas del comportamiento y los controles.
- `prompts`: instrucciones editables para los modelos.
- `docs`: documentación para personas, incluido el diagrama HTML generado con Archify y su fuente JSON.
- `data`: entradas sintéticas. El corpus que consume el RAG se separa de la documentación del tema.
- `outputs`: bases generadas, índices, trazas y comprobaciones locales. No se publica en Git.

Cada README de tema explicará el recorrido, los objetivos, los comandos y los resultados esperados. Su `main.py` ofrecerá un menú numerado con opción de salir; también será posible ejecutar cada lección directamente.

## Configuración y modelos

Los temas incluirán `.env.example` con los nombres de sus variables, sin claves reales. La configuración local se guardará en un `.env` ignorado por Git, en la raíz del tema.

Antes de ejecutar una lección, revisar su proveedor, modelo, requisitos y posible consumo de API. No se cambiará de proveedor automáticamente. Las lecciones no tendrán un modo simulado; las respuestas falsas se usarán únicamente en pruebas.

No publicar credenciales, datos reales ni salidas que los contengan.
