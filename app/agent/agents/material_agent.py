from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.material import search_materials, add_material, list_materials
from langgraph.prebuilt import ToolNode

# tools of material agent
MATERIAL_AGENT_TOOLS = [search_materials, add_material, list_materials]

tool_node = ToolNode(MATERIAL_AGENT_TOOLS)


def material_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(MATERIAL_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_material_agent():
    builder = StateGraph(AgentState)

    builder.add_node("material_agent", material_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "material_agent")
    builder.add_conditional_edges("material_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "material_agent")

    return builder.compile()
