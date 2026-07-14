from langgraph.graph import StateGraph, START, END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model


def chat_agent_node(state: AgentState):
    # init model
    llm = init_model()

    # get resp and return
    resp = llm.invoke(state["messages"])
    return {"messages": [resp]}


# bulid graph
def build_chat_agent():
    builder = StateGraph(AgentState)

    builder.add_node("chat_agent",chat_agent_node)

    builder.add_edge(START, "chat_agent")
    builder.add_edge("chat_agent",END)

    return builder.compile()