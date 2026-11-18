"""Índice léxico local con metadatos de vigencia por fragmento."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re

from caso3.config import CORPUS, OUTPUTS
from caso3.contratos import ReglaCitada


@dataclass(frozen=True)
class Norma:
    fuente: str
    version: str
    vigente_desde: date
    vigente_hasta: date | None
    umbral_cotizaciones: Decimal
    vigencia_certificado_dias: int
    umbral_firma: Decimal
    firmante_menor: str
    firmante_mayor: str

    def vigente(self, fecha: date) -> bool:
        return self.vigente_desde <= fecha and (self.vigente_hasta is None or fecha <= self.vigente_hasta)


@dataclass(frozen=True)
class Fragmento:
    norma: Norma
    texto: str

    def citar(self) -> ReglaCitada:
        return ReglaCitada(fuente=self.norma.fuente, version=self.norma.version,
                          vigente_desde=self.norma.vigente_desde, texto=self.texto)


def indexar(corpus: Path | None = None) -> list[Fragmento]:
    fragments = []
    for path in sorted((corpus or CORPUS / "normativa").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"```json\s*(.*?)```", text, re.S)
        if not match:
            raise ValueError(f"Norma sin metadatos: {path.name}")
        meta = json.loads(match[1])
        meta["vigente_desde"] = date.fromisoformat(meta["vigente_desde"])
        meta["vigente_hasta"] = date.fromisoformat(meta["vigente_hasta"]) if meta["vigente_hasta"] else None
        for key in ("umbral_cotizaciones", "umbral_firma"):
            meta[key] = Decimal(meta[key])
            if not meta[key].is_finite() or meta[key] <= 0:
                raise ValueError("Umbral normativo inválido.")
        rule = Norma(**meta)
        if rule.fuente != path.name or (rule.vigente_hasta and rule.vigente_hasta < rule.vigente_desde):
            raise ValueError("Fuente o intervalo normativo inválido.")
        if rule.vigencia_certificado_dias < 1:
            raise ValueError("Vigencia de certificados inválida.")
        for section in re.split(r"(?m)^## ", text[match.end():]):
            if section.strip():
                fragments.append(Fragmento(rule, section.strip()))
    if not fragments:
        raise ValueError("El corpus normativo está vacío.")
    return fragments


if __name__ == "__main__":
    fragments = indexar()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "indice.json").write_text(json.dumps([
        dict(fuente=f.norma.fuente, version=f.norma.version, vigente_desde=f.norma.vigente_desde.isoformat(),
             vigente_hasta=f.norma.vigente_hasta.isoformat() if f.norma.vigente_hasta else None, texto=f.texto)
        for f in fragments
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Índice local: {len(fragments)} fragmentos.")
