# %% [markdown]
# # Contratos y vigencia antes de usar el modelo
#
# Objetivos: normalizar sin perder precisión y observar cómo una regla vieja
# puede ganar por relevancia si no se filtra la vigencia.
# Prerrequisitos: Python 3.11 y dependencias del repositorio. No requiere claves.
# Comando: python 07_caso3\src\leccion_local.py
#
# %% Valores observables y comprobaciones
from datetime import date
from decimal import Decimal

from caso3.herramientas.normalizar import parse_fecha, parse_monto
from caso3.rag.recuperar import recuperar_regla, recuperar_sin_filtro


def main():
    amount = parse_monto("1.200.000")
    when = parse_fecha("21 de mayo de 2026")
    print("Monto:", amount, "| tipo:", type(amount).__name__)
    print("Fecha:", when, "| tipo:", type(when).__name__)
    old = recuperar_sin_filtro("umbral cotizaciones")[0]
    current = recuperar_regla("umbral cotizaciones", when)[0]
    print("Sin filtrar vigencia:", old.fuente)
    print("Con vigencia de 2026:", current.fuente)
    assert amount == Decimal("1200000")
    assert when == date(2026, 5, 21)
    assert old.fuente == "manual-2024.md"
    assert current.fuente == "circular-2026.md"
    print("Comprobaciones locales correctas. No se llamó a ningún modelo.")


# %% [markdown]
# Producción: versionar y revisar el corpus; reemplazar el índice léxico cuando
# el volumen lo justifique, sin eliminar los filtros temporales.
if __name__ == "__main__":
    main()
