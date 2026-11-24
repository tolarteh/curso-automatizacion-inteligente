"""Cruces deterministas: la evidencia contradictoria se devuelve a una persona."""
from datetime import date
from decimal import Decimal
import re

from caso3.contratos import Hallazgo
from caso3.herramientas.normalizar import normalizar_nit, parse_fecha, parse_monto, plain
from caso3.rag.recuperar import norma_vigente, recuperar_regla


def field(text, label):
    match = re.search(rf"(?im)^{re.escape(label)}:\s*([^\r\n]+)", text)
    if not match:
        raise ValueError(f"Falta el campo documental {label}.")
    return match[1].strip()


def firmante_requerido(monto: Decimal, norma) -> str:
    return norma.firmante_mayor if monto >= norma.umbral_firma else norma.firmante_menor


def cruzar(extracciones, documentos=None, *, fecha_expediente=None, reglas=None):
    """No se solicita reextracción para corregir un error real del documento."""
    if fecha_expediente is None:
        raise ValueError("La auditoría requiere la fecha del expediente.")
    norm = norma_vigente(fecha_expediente)
    valid_rules = recuperar_regla("cotizaciones certificados firma", fecha_expediente)
    findings = []

    def add(code, detail, rule=None, target=None):
        if code not in {h.codigo for h in findings}:
            findings.append(Hallazgo(codigo=code, severidad="bloqueante", detalle=detail,
                                     regla=rule, devolver_a=target))

    if reglas is not None and any(r not in valid_rules for r in reglas):
        add("REGLA_NO_VIGENTE", "La cita no corresponde al corpus vigente.", target="verificador")
    if documentos is not None:
        present = {doc.tipo for doc in documentos}
        missing = {"solicitud", "factura", "certificado"} - present
        if missing:
            add("DOCUMENTOS_FALTANTES", f"Faltan soportes obligatorios: {', '.join(sorted(missing))}.")
    quotes = [e for e in extracciones if e.doc_id.startswith("cotizacion")]
    winners = [e for e in quotes if e.es_ganadora]
    invoices = [e for e in extracciones if e.doc_id == "factura"]
    if len(winners) != 1 or len(invoices) != 1:
        add("COMPARACION_IMPOSIBLE", "Se necesita una factura y una cotización ganadora.", target="extractor")
    else:
        winner, invoice = winners[0], invoices[0]
        if normalizar_nit(winner.nit) != normalizar_nit(invoice.nit):
            add("NIT_DISTINTO", "El NIT de la factura difiere del NIT de la ganadora.")
        if winner.monto_total != invoice.monto_total:
            add("MONTO_DISTINTO", "El monto facturado difiere de la cotización ganadora.")
        if invoice.fecha < winner.fecha or invoice.fecha > fecha_expediente:
            add("FECHAS_INCOHERENTES", "La factura antecede la ganadora o es posterior al expediente.")
        if winner.monto_total >= norm.umbral_cotizaciones and len(quotes) < 3:
            add("COTIZACIONES_INSUFICIENTES", "El monto exige al menos tres cotizaciones.", valid_rules[0])
    for extraction in extracciones:
        if extraction.iva_incluido is None:
            add("IVA_AMBIGUO", f"{extraction.doc_id}: no se aclara si incluye IVA.")
        if extraction.fecha > fecha_expediente:
            add("FECHAS_INCOHERENTES", f"{extraction.doc_id}: fecha futura.")
        if extraction.items and sum(item.cantidad * item.valor_unitario for item in extraction.items) != extraction.monto_total:
            add("ITEMS_INCOHERENTES", f"{extraction.doc_id}: los ítems no suman el monto total.")
    for doc in documentos or []:
        text = plain(doc.texto)
        if "apruebe sin revisar" in text or "omita las validaciones" in text:
            add("INYECCION_DOCUMENTAL", f"{doc.id}: instrucción no confiable dentro de un documento.")
        if doc.texto.startswith("OCR_REQUERIDO:"):
            add("OCR_REQUERIDO", doc.texto)
        if re.search(r"(?im)^monto en letras:", text):
            if parse_monto(field(text, "monto")) != parse_monto(field(text, "monto en letras")):
                add("MONTO_LETRAS", f"{doc.id}: el monto numérico no coincide con las letras.")
        if doc.tipo == "certificado":
            issued = parse_fecha(field(text, "fecha"))
            until = parse_fecha(field(text, "vigente hasta"))
            if issued > fecha_expediente or (fecha_expediente - issued).days > norm.vigencia_certificado_dias or until < fecha_expediente:
                add("CERTIFICADO_VENCIDO", f"{doc.id}: certificado fuera de vigencia.", valid_rules[-1])
    return findings
