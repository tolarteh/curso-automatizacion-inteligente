"""Contratos locales para reescritura, relevancia y fidelidad."""
from context import format_context, valid_citations
from model import read_prompt

REWRITE_SCHEMA = {"type": "object", "additionalProperties": False,
                  "required": ["consulta", "palabras_clave"], "properties": {
                      "consulta": {"type": "string"},
                      "palabras_clave": {"type": "array", "minItems": 3, "maxItems": 6,
                                        "items": {"type": "string"}}}}
GRADE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["relevantes"],
                "properties": {"relevantes": {"type": "array", "maxItems": 4,
                                             "items": {"type": "integer"}}}}
VERIFY_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["sustentada", "problemas"], "properties": {
                     "sustentada": {"type": "boolean"},
                     "problemas": {"type": "array", "items": {"type": "string"}}}}


def fields(value, names: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError("La salida del modelo no cumple los campos del contrato.")


def rewrite(llm, question: str, previous: str = "") -> dict:
    result = llm.chat_json([
        {"role": "system", "content": read_prompt("reescribir.txt")},
        {"role": "user", "content": f"Pregunta: {question}\nConsulta anterior sin evidencia: {previous}"},
    ], REWRITE_SCHEMA, name="consulta", purpose="reescribir")
    fields(result, {"consulta", "palabras_clave"})
    query, keywords = result["consulta"], result["palabras_clave"]
    if (not isinstance(query, str) or not query.strip() or not isinstance(keywords, list)
            or not 3 <= len(keywords) <= 6
            or any(not isinstance(word, str) or not word.strip() for word in keywords)):
        raise ValueError("Consulta o palabras clave inválidas.")
    return result


def lexical_query(question: str, rewritten: dict) -> str:
    return f"{question} {rewritten['consulta']} {' '.join(rewritten['palabras_clave'])}"


def grade(llm, question: str, hits) -> list:
    if not hits:
        return []
    result = llm.chat_json([
        {"role": "system", "content": read_prompt("calificar.txt")},
        {"role": "user", "content": f"Pregunta: {question}\nContexto JSON:\n{format_context(hits)}"},
    ], GRADE_SCHEMA, name="relevancia", purpose="calificar")
    fields(result, {"relevantes"})
    selected = result["relevantes"]
    if (not isinstance(selected, list) or len(selected) > 4
            or any(type(n) is not int or not 1 <= n <= len(hits) for n in selected)):
        raise ValueError("La selección contiene posiciones inválidas o demasiados fragmentos.")
    if len(set(selected)) != len(selected):
        raise ValueError("La selección de fragmentos contiene posiciones repetidas.")
    return [hits[n - 1] for n in selected]


def verify(llm, question: str, text: str, hits) -> dict:
    if not valid_citations(text, hits):
        return {"sustentada": False, "problemas": ["Citas ausentes o fuera del contexto."]}
    result = llm.chat_json([
        {"role": "system", "content": read_prompt("verificar.txt")},
        {"role": "user", "content": f"Contexto JSON:\n{format_context(hits)}\n"
         f"Pregunta: {question}\nRespuesta: {text}"},
    ], VERIFY_SCHEMA, name="verificacion", purpose="verificar")
    fields(result, {"sustentada", "problemas"})
    supported, problems = result["sustentada"], result["problemas"]
    if (type(supported) is not bool or not isinstance(problems, list)
            or any(not isinstance(problem, str) or not problem.strip() for problem in problems)):
        raise ValueError("Tipos inválidos en la verificación.")
    if supported == bool(problems):
        raise ValueError("Verificación contradictoria o sin explicación del rechazo.")
    return result
