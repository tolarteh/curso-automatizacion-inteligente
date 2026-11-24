# %% [markdown]
# # Ejecución y cierre
#
# Objetivos: comprobar antes/después; reconocer fallo parcial; reconciliar
# cambio aplicado sin registro. Prerrequisitos: plan y dos aprobaciones.
# Ejecutar: python 05_caso2\src\03_ejecucion_y_cierre.py
# Ejecución del caso: añadir --case HASH --today 2026-10-14.
#
# Intuición: "Cuenta bloqueada" se demuestra consultando el estado, no con una
# frase del agente. El proveedor es Git simulado, no GitHub.com.

# %%
import argparse
import json
from contracts import ROOT, read_json
from execution import apply_action


def demo():
    before = read_json(ROOT / "data" / "inventory.json")
    action = {"kind": "block", "target": "ana.dev"}
    after = apply_action(before, "ana.dev", action)
    print("Antes:", before["users"]["ana.dev"]["blocked"])
    print("Después:", after["users"]["ana.dev"]["blocked"])
    assert after["users"]["ana.dev"]["blocked"]
    assert not before["users"]["ana.dev"]["blocked"]
    assert apply_action(after, "ana.dev", action) == after
    print("Repetir la operación no cambia de nuevo el estado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--today", default="2026-10-14")
    parser.add_argument("--fail-after", type=int)
    parser.add_argument("--crash-after-change", type=int)
    parser.add_argument("--level", choices=["metrics", "traces"], default="metrics")
    args = parser.parse_args()
    if args.case:
        from service import run_execution
        case = run_execution(args.case, args.today, args.fail_after, args.crash_after_change, args.level)
        print(json.dumps(case, indent=2, ensure_ascii=False))
    else:
        demo()

# %% [markdown]
# ## Paso a producción
#
# No prometemos exactly-once. Un diario pending permite contrastar un corte
# entre cambio y registro. Si el inventario no coincide con la transición
# esperada se invalida el plan. La ejecución real necesita un mapeo específico
# de permisos y operaciones para cada organización o Enterprise.
#
# Recapitulación: no éxito sin verificación; fallos y pendientes quedan en el
# cierre; la notificación es un borrador local, nunca un envío automático.
