"""La pausa no modifica Git. El ejecutor vuelve a comprobar los permisos."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from planning import approve
from contracts import Status


class State(TypedDict):
    case: dict


def build_graph(saver):
    def approval_node(state):
        case = state["case"]
        if case["status"] != Status.PENDING:
            return {"case": case}
        decision = interrupt({"case_id": case["case_id"], "plan": case["plan"],
                              "approved_roles": [item["role"] for item in case["approvals"]]})
        approve(case, decision["actor"], decision["role"], decision["decision"],
                decision["hash"], decision["version"])
        return {"case": case}

    def route(state):
        case = state["case"]
        if case["status"] == Status.REJECTED or len(case["approvals"]) == 2:
            return END
        return "approval"

    builder = StateGraph(State)
    builder.add_node("approval", approval_node)
    builder.add_edge(START, "approval")
    builder.add_conditional_edges("approval", route)
    return builder.compile(checkpointer=saver)
