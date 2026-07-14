from langgraph.graph import StateGraph,START,END
from app.agent.agent_kernel.state import AgentState
from app.agent.agent_kernel.config import init_model
from app.agent.tools.course import (
    search_courses, list_all_courses, create_course,
    update_course, delete_course,
)
from langgraph.prebuilt import ToolNode

#tools of course agent
COURSE_AGENT_TOOLS = [
    search_courses,
    list_all_courses,
    create_course,
    update_course,
    delete_course,
]

tool_node = ToolNode(COURSE_AGENT_TOOLS)

def course_agent_node(state:AgentState):
    #init model
    llm=init_model()
    llm=llm.bind_tools(COURSE_AGENT_TOOLS)

    #get resp and return
    resp=llm.invoke(state["messages"])
    return {"messages":[resp]}

def should_continue(state: AgentState):
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tools"
    return END

#bulid graph
def build_course_agent():
    builder=StateGraph(AgentState)

    builder.add_node("course_agent",course_agent_node)
    builder.add_node("tools",tool_node)

    builder.add_edge(START,"course_agent")
    builder.add_conditional_edges("course_agent",should_continue,{"tools":"tools",END:END})
    builder.add_edge("tools", "course_agent")

    return builder.compile()
