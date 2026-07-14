from langgraph.graph import StateGraph,START,END
from app.agent.agent_kernel.config import init_model
from app.agent.agent_kernel.state import AgentState

"""
看对话历史，输出学习计划。纯 LLM节点，没循环。
"""

def plan_agent_node(state:AgentState):
    llm=init_model()

    resp=llm.invoke(state["messages"])
    return {"messages":[resp]}

# bulid graph
def build_plan_agent():
    builder = StateGraph(AgentState)

    builder.add_node("plan_agent_node", plan_agent_node)

    builder.add_edge(START, "plan_agent_node")
    builder.add_edge("plan_agent_node", END)

    return builder.compile()
