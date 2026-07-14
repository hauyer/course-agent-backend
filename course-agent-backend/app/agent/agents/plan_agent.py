from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.config import init_model
from app.agent.agent_kernel.state import AgentState
from langgraph.prebuilt import ToolNode
from app.agent.tools.plan import (
    create_study_plan,
    list_study_plans,
    get_study_plan_detail,
    update_study_plan_status,
    delete_study_plan,
    create_task,
    list_tasks,
    update_task_status,
    delete_task,
    get_dashboard_overview,
)

# tools of plan agent
PLAN_AGENT_TOOLS = [
    create_study_plan,
    list_study_plans,
    get_study_plan_detail,
    update_study_plan_status,
    delete_study_plan,
    create_task,
    list_tasks,
    update_task_status,
    delete_task,
    get_dashboard_overview,
]

tool_node = ToolNode(PLAN_AGENT_TOOLS)

def plan_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(PLAN_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_plan_agent():
    builder = StateGraph(AgentState)

    builder.add_node("plan_agent", plan_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "plan_agent")
    builder.add_conditional_edges("plan_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "plan_agent")

    return builder.compile()