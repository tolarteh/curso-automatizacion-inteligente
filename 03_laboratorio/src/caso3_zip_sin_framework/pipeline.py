"""El pipeline completo del caso 3: pasos fijos, en orden, sin agente ni framework.

    ZIP → abrir_zip (seguro) → texto → extraer_documento (modelo + evaluador, por soporte)
        → decidir (reglas de PR-FIN-012) → resumen trazable (JSON + Markdown con SHA-256)

El orden no lo decide el modelo: es un for. El modelo solo convierte texto en campos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .extraccion import extraer_documento
from .reglas import decidir, pesos
from .zip_seguro import abrir_zip


def procesar_zip(path: Path, client, backend, trace=None, mostrar=print) -> dict:
    soportes, omitidos = abrir_zip(path)
    mostrar(f"1-2. ZIP abierto: {len(soportes)} soportes legibles" + (f", {len(omitidos)} omitidos" if omitidos else ""))
    documentos = []
    for soporte in soportes:  # un trabajador por documento (en serie: cuota por minuto de Groq)
        resultado = extraer_documento(client, backend, soporte.nombre, soporte.texto, trace)
        documentos.append({**resultado, "sha256": soporte.sha256, "texto": soporte.texto})
        estado = "verificado" if resultado["verificado"] else "NO verificado"
        tipo = (resultado["extraccion"] or {}).get("tipo")
        mostrar(f"3. {soporte.nombre}: {tipo} · {estado} · intentos {resultado['intentos']}")
        for problema in resultado["problemas"]:
            mostrar(f"     problema: {problema}")
    decision = decidir(documentos)
    if decision["cruce"]:
        cruce = {k: pesos(v) for k, v in decision["cruce"].items() if isinstance(v, int) and not isinstance(v, bool)}
        mostrar("4. Cruce en código: solicitado {monto_solicitado} · pagado {suma_pagada} · diferencia "
                "{diferencia} · tolerancia {tolerancia}".format(**cruce))
    mostrar(f"5. Reglas de PR-FIN-012: {decision['decision']}")
    return {"zip": path.name, "procesado": datetime.now(timezone.utc).isoformat(), "modelo": backend.model,
            "omitidos": omitidos, "documentos": [{k: v for k, v in d.items() if k != "texto"} for d in documentos],
            **decision}


def resumen_markdown(resultado: dict) -> str:
    """Documento resumen de PR-FIN-012, sección 5: soportes con huella, montos y decisión."""
    lineas = [f"# Resumen de la solicitud {resultado['zip']}", "",
              f"Decisión sugerida: **{resultado['decision']}**  ", f"Responsable: {resultado['responsable']}  ",
              f"Procesado: {resultado['procesado']} con {resultado['modelo']}", "",
              "| Soporte | Tipo | Verificado | Intentos | SHA-256 |", "|---|---|---|---|---|"]
    for doc in resultado["documentos"]:
        tipo = (doc["extraccion"] or {}).get("tipo", "-")
        lineas.append(f"| {doc['nombre']} | {tipo} | {'sí' if doc['verificado'] else 'no'} | {doc['intentos']} "
                      f"| `{doc['sha256']}` |")
    cruce = resultado.get("cruce")
    if cruce:
        lineas += ["", "| Monto solicitado | Suma pagada | Diferencia | Tolerancia |", "|---|---|---|---|",
                   f"| {pesos(cruce['monto_solicitado'])} | {pesos(cruce['suma_pagada'])} "
                   f"| {pesos(cruce['diferencia'])} | {pesos(cruce['tolerancia'])} |"]
    if resultado["motivos"]:
        lineas += ["", "## Motivos", *[f"- {m}" for m in resultado["motivos"]]]
    if resultado["observaciones"] or resultado["omitidos"]:
        lineas += ["", "## Observaciones", *[f"- {o}" for o in resultado["observaciones"] + resultado["omitidos"]]]
    return "\n".join(lineas) + "\n"


def guardar(resultado: dict, carpeta: Path) -> tuple[Path, Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / Path(resultado["zip"]).stem
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    json_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(resumen_markdown(resultado), encoding="utf-8")
    return json_path, md_path
