from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.concept import explain_concept
from langgraph.prebuilt import ToolNode

# tools of concept agent
CONCEPT_AGENT_TOOLS = [explain_concept]

tool_node = ToolNode(CONCEPT_AGENT_TOOLS)


def concept_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(CONCEPT_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_concept_agent():
    builder = StateGraph(AgentState)

    builder.add_node("concept_agent", concept_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "concept_agent")
    builder.add_conditional_edges("concept_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "concept_agent")

    return builder.compile()