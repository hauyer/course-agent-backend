import os
from dotenv import load_dotenv
from app.agent.agent_kernel.config import init_model
from app.agent.agent_kernel.state import AgentState
from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage

load_dotenv()

MAX_TOKENS=int(os.getenv("MAX_TOKENS", "20000"))
COMPRESS_PROMPT=[SystemMessage(
          content="用一段中文总结以下对话，提取课程名、概念、用户水平，不超过150字。"
      )]

def estimate_tokens(messages:list) -> int:
    total=0
    for m in messages:
        total+=len(m.content)//2
    return total

# compress contextual window
def compress_node(state:AgentState) -> dict:
    messages=state["messages"]
    if estimate_tokens(messages) <= MAX_TOKENS:
        return {}

    # 找最后一条 HumanMessage 的位置
    last_human_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    if last_human_idx is None:
        return {}

    #compress contextual window
    compress_prompt=COMPRESS_PROMPT+messages[:last_human_idx]
    llm=init_model()
    summary=llm.invoke(compress_prompt)

    # 使用 RemoveMessage 配合 add_messages reducer 真正移除已摘要的历史，
    # 避免旧实现的原消息 + 摘要重复累积。
    removals = [RemoveMessage(id=item.id) for item in messages if item.id]
    recent_messages = [
        item.model_copy(update={"id": None})
        for item in messages[last_human_idx:]
    ]
    return {
        "messages": removals
        + [SystemMessage(content=f"[历史摘要] {summary.content}")]
        + recent_messages
    }
