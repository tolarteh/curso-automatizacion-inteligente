# %% [markdown]
# # Reto en parejas: cuatro fronteras del sistema
#
# Objetivos: conservar tipos, aplicar vigencia y frenar revisiones ilimitadas.
# Prerrequisitos: Python, Decimal, date y lectura del README del tema.
# Comando: python 07_caso3\src\estudiante\comprobar.py
# Resultado inicial esperado: cuatro errores TODO, no una solución simulada.
#
# %% Completar sin copiar la solución
def parse_amount(text):
    # Pista: el punto separa miles en "1.200.000"; devolver Decimal, no float.
    raise NotImplementedError("TODO normalizador de montos")


def filter_rules(rules, when):
    # Pista: vigente_hasta puede ser None; los dos extremos son inclusivos.
    raise NotImplementedError("TODO filtro de vigencia")


def request_revision(state):
    # Pista: leer y actualizar vueltas en el estado; nunca superar dos.
    raise NotImplementedError("TODO límite de vueltas")


def pass_power(outcomes, k):
    # Pista: alguna corrida correcta no equivale a todas las k correctas.
    raise NotImplementedError("TODO métrica pass^k")


# %% [markdown]
# Producción: estos controles deben probarse también contra handoffs reales,
# interrupciones y respuestas inválidas, no solo sobre entradas ideales.
