from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.learning import (
    create_learning_record,
    list_learning_records,
    get_learning_summary,
    get_course_progress,
    delete_learning_record,
)

from langgraph.prebuilt import ToolNode

# tools of learning agent
LEARNING_AGENT_TOOLS = [
    create_learning_record,
    list_learning_records,
    get_learning_summary,
    get_course_progress,
    delete_learning_record,
]

tool_node = ToolNode(LEARNING_AGENT_TOOLS)


def learning_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(LEARNING_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_learning_agent():
    builder = StateGraph(AgentState)

    builder.add_node("learning_agent", learning_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "learning_agent")
    builder.add_conditional_edges("learning_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "learning_agent")

    return builder.compile()