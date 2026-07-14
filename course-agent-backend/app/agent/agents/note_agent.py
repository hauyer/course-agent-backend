from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.note import (
    create_note,
    search_notes,
    get_note_detail,
    update_note,
    delete_note,
    sync_note_to_obsidian,
    sync_note_to_notion,
    list_note_sync_records,
)

from langgraph.prebuilt import ToolNode

# tools of note agent
NOTE_AGENT_TOOLS = [
    create_note,
    search_notes,
    get_note_detail,
    update_note,
    delete_note,
    sync_note_to_obsidian,
    sync_note_to_notion,
    list_note_sync_records,
]

tool_node = ToolNode(NOTE_AGENT_TOOLS)


def note_agent_node(state: AgentState):
    # init model
    llm = init_model()
    llm = llm.bind_tools(NOTE_AGENT_TOOLS)

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END


# bulid graph
def build_note_agent():
    builder = StateGraph(AgentState)

    builder.add_node("note_agent", note_agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "note_agent")
    builder.add_conditional_edges("note_agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "note_agent")

    return builder.compile()