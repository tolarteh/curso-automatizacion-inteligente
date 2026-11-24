# %% [markdown]
# # Plan y aprobación
#
# Objetivos: enumerar acciones desde inventario; ligar aprobación a hash y
# versión; reanudar un checkpoint. Prerrequisitos: lección 1 y SHA-256.
# Ejecutar: python 05_caso2\src\02_plan_y_aprobacion.py
#
# Intuición: "apruebo la baja" no precisa qué acciones se revisaron.
# El hash cambia cuando cambia el plan, incluido inventario y advertencias.

# %%
import argparse
import json
from contracts import ROOT, read_json
from extraction import structured
from planning import build_plan, plan_hash


def demo():
    request = structured(read_json(ROOT / "data" / "messages.json")[0]["body"])
    plan = build_plan(request, read_json(ROOT / "data" / "inventory.json"))
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    assert len(plan["actions"]) == 4
    assert plan["hash"] == plan_hash(plan)
    print("Cuatro acciones simuladas; transferencia de propietario sigue pendiente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--actor")
    parser.add_argument("--role", choices=["manager", "security"])
    parser.add_argument("--decision", choices=["approve", "reject"], default="approve")
    parser.add_argument("--hash")
    parser.add_argument("--version", type=int)
    parser.add_argument("--replan", action="store_true")
    parser.add_argument("--today", default="2026-10-14")
    parser.add_argument("--level", choices=["metrics", "traces"], default="metrics")
    args = parser.parse_args()
    if not args.case:
        demo()
    else:
        from service import decide, replan
        if args.replan:
            case = replan(args.case, args.today, args.level)
        else:
            if not all([args.actor, args.role, args.hash, args.version]):
                parser.error("Aprobar requiere --actor --role --hash --version.")
            case = decide(args.case, args.actor, args.role, args.decision, args.hash, args.version, args.level)
        print(json.dumps(case, indent=2, ensure_ascii=False))

# %% [markdown]
# ## Paso a producción
#
# interrupt reinicia el nodo al reanudar: ningún cambio Git ocurre antes de la
# pausa. SQLite conserva estado, MLflow enlaza segmentos pero no los autoriza.
# CLI declara actores; producción necesita autenticación y roles comprobados.
#
# Recapitulación: revisar acciones y pendientes; aprobar versión concreta;
# rechazar corta el recorrido; inventario nuevo exige dos aprobaciones nuevas.
