from langgraph.graph import StateGraph,START,END
from app.agent.agent_kernel.config import init_model
from app.agent.agent_kernel.state import AgentState
from app.agent.agents.chat_agent import build_chat_agent
from app.agent.agents.course_agent import build_course_agent
from app.agent.agents.concept_agent import build_concept_agent
from app.agent.agents.material_agent import build_material_agent
from app.agent.agents.plan_agent import build_plan_agent
from app.agent.agents.context import compress_node
from langchain_core.messages import SystemMessage
from app.agent.agent_kernel.memory import memory_node,save_node

SUPERVISOR_PROMPT = """你是课程学习助手调度中心。分析用户意图，只回复以下 6 个词之一：

  course   — 操作课程（查询、搜索、创建、列出课程）
  material — 操作学习资料（查看、添加资料）
  concept  — 解释概念（"什么是XX""解释XX"）
  plan     — 规划推荐（"推荐学习路径""下一步学什么""制定计划"）
  chat     — 闲聊问答（打招呼、问你是谁、能做什么、不涉及数据和工具）
  FINISH   — 对话已完成，无需继续

  决策规则（按顺序判断）：
  1. 如果用户的最新消息是结束语（"谢谢""好的""拜拜""没了""没事了"）且上一轮已被回复 → FINISH
  2. 如果用户追问或延续上一轮内容（"继续""详细说说""还有吗""举个例子""为什么""帮我看看""怎么说""那我该""所以"）→ 根据上下文判断：上一轮在讲概念→concept，在讲规划→plan，在讲课程→course，其他→chat
  3. 如果用户的最新消息涉及课程操作 → course 或 material
  4. 如果用户的最新消息涉及知识解释 → concept
  5. 如果用户的最新消息涉及学习规划 → plan
  6. 如果用户的消息是闲聊 → chat
  7. 以上都不匹配 → chat（绝不静默结束）

  严格只回复一个词。"""

VALID_ROUTES = {"course", "material", "concept", "plan", "chat", "FINISH"}


def supervisor_agent(state: AgentState):
    llm = init_model()
    messages = [SystemMessage(content=SUPERVISOR_PROMPT)] + state["messages"]
    resp = llm.invoke(messages)
    raw = resp.content.strip()
    # 只取第一行第一词，去掉中文标点，防止 LLM 输出 "course。" 之类
    first_word = raw.split("\n")[0].split()[0] if raw else ""
    first_word = first_word.strip("。，！？,.!?")
    if first_word not in VALID_ROUTES:
        first_word = "FINISH"
    return {"next": first_word}

#edge route
def conditional_route(state:AgentState):
    return state["next"]


# bulid graph
def build_supervisor(checkpointer,store):
    builder = StateGraph(AgentState)

    #add agent node
    builder.add_node("supervisor_agent", supervisor_agent)
    builder.add_node("course_agent_node",build_course_agent())
    builder.add_node("concept_agent_node", build_concept_agent())
    builder.add_node("material_agent_node", build_material_agent())
    builder.add_node("plan_agent_node", build_plan_agent())
    builder.add_node("chat_agent_node",build_chat_agent())
    builder.add_node("memory_node",memory_node)
    builder.add_node("save_node",save_node)
    builder.add_node("compress_node",compress_node)


    #add edge
    builder.add_edge(START, "memory_node")
    builder.add_edge("memory_node","supervisor_agent")

    builder.add_conditional_edges(
        "supervisor_agent",
        conditional_route,
        {
            "course":"course_agent_node",
            "material":"material_agent_node",
            "concept":"concept_agent_node",
            "plan":"plan_agent_node",
            "FINISH":END,
            "chat":"chat_agent_node"
        }
    )


    #loop
    builder.add_edge("plan_agent_node","save_node")
    builder.add_edge("course_agent_node", "save_node")
    builder.add_edge("concept_agent_node", "save_node")
    builder.add_edge("material_agent_node", "save_node")
    builder.add_edge("save_node","compress_node")
    builder.add_edge( "compress_node","supervisor_agent")

    # start - supervisor - chat - end /no loop
    builder.add_edge("chat_agent_node",END)


    return builder.compile(checkpointer=checkpointer,store=store)
