from copy import deepcopy
from types import SimpleNamespace

CORRECT_SQL = """
SELECT r.name AS region, COUNT(*) AS retrasados
FROM orders o JOIN regions r ON r.region_id = o.region_id
WHERE o.promised_at >= '2026-03-01' AND o.promised_at < '2026-04-01'
AND (o.delivered_at > o.promised_at OR o.delivered_at IS NULL)
AND o.status != 'cancelado'
GROUP BY r.name ORDER BY retrasados DESC
"""


def response(text=None, calls=None):
    tools = [SimpleNamespace(id=f"call-{index}", type="function",
                             function=SimpleNamespace(name=name, arguments=arguments))
             for index, (name, arguments) in enumerate(calls or [])]
    message = SimpleNamespace(content=text, tool_calls=tools)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


class FakeLlm:
    """Doble exclusivo de pruebas; nunca se importa desde src."""
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, *, purpose, **kwargs):
        self.calls.append({"messages": deepcopy(messages), "purpose": purpose, **kwargs})
        return next(self.responses)
