from langgraph.store.memory import InMemoryStore
from app.agent.agent_kernel.state import AgentState
from langchain_core.messages import SystemMessage,HumanMessage

#only one store to manage memory
store=InMemoryStore()

MEMORY_PROMPT = "[长期记忆] 用户水平={level}，兴趣={interests}，已学={courses}"

#get last memory and if not exist give default
def _get_or_default(namespace:tuple,key:str,default):
    item=store.get(namespace,key)
    if item is not None:
        return item.value
    store.put(namespace,key,default)
    return default

def memory_node(state:AgentState)->dict:
    #init user's memory or get memory of user

    uid=state.get("user_id","anonymous")

    level=_get_or_default(("users",uid,"profile"),"level","beginner")
    interests=_get_or_default(("users",uid,"profile"),"interests",[])
    courses=_get_or_default(("users",uid,"profile"),"courses",[])

    #return system prompt with long memory
    text=MEMORY_PROMPT.format(level=level,interests=interests,courses=courses)
    return {"messages":[SystemMessage(content=text)]}

# ---------- 从对话中提取用户画像 ----------
import re

LEVEL_RULES = {
    "beginner":     ["入门", "零基础", "刚开始", "新手", "初学"],
    "intermediate": ["学过", "了解过", "用过", "写过", "会", "学了"],
    "advanced":     ["精通", "深入", "熟练", "多年经验", "专家"],
}

INTEREST_TOPICS = [
    "Python", "机器学习", "深度学习", "神经网络", "NLP", "CV",
    "Java", "Go", "Rust", "前端", "后端", "数据科学",
    "数学", "英语", "线性代数", "概率论", "统计学", "SQL",
]


def _extract_level(messages: list) -> str | None:
    """扫描用户消息，返回匹配到的最高水平，未匹配返回 None"""
    best = None
    best_rank = -1
    ranks = {"beginner": 0, "intermediate": 1, "advanced": 2}
    for msg in messages:
        if isinstance(msg, HumanMessage):
            text = msg.content
            for level, keywords in LEVEL_RULES.items():
                if any(kw in text for kw in keywords):
                    if ranks[level] > best_rank:
                        best = level
                        best_rank = ranks[level]
    return best


def _extract_interests(messages: list) -> list[str]:
    """扫描用户消息，提取匹配的兴趣标签"""
    found = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            for topic in INTEREST_TOPICS:
                if topic in msg.content and topic not in found:
                    found.append(topic)
    return found


def _extract_courses(messages: list) -> list[str]:
    """扫描用户消息，提取'学过/学了/完成了/上过'后面提到的课程名"""
    found = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            matches = re.findall(
                r"(?:学过|学了|完成了|上过)\s*(.+?)(?:[，。！？,\n]|$)",
                msg.content,
            )
            for m in matches:
                name = m.strip()
                if name and name not in found:
                    found.append(name)
    return found


# ---------- 节点函数 ----------


#save memeory in store
def save_node(state:AgentState)->dict:
    uid=state.get("user_id","anonymous")
    namespace=("users",uid,"profile")

    # 读当前值
    level     = _get_or_default(namespace, "level", "beginner")
    interests = _get_or_default(namespace, "interests", [])
    courses   = _get_or_default(namespace, "courses", [])

    # 从本轮消息提取
    new_level     = _extract_level(state["messages"])
    new_interests = _extract_interests(state["messages"])
    new_courses   = _extract_courses(state["messages"])

    # level 只升不降
    ranks = {"beginner": 0, "intermediate": 1, "advanced": 2}
    if new_level and ranks.get(new_level, 0) > ranks.get(level, 0):
        store.put(namespace, "level", new_level)

    # interests 去重合并
    for t in new_interests:
        if t not in interests:
            interests.append(t)
    store.put(namespace, "interests", interests)

    # courses 去重合并
    for c in new_courses:
        if c not in courses:
            courses.append(c)
    store.put(namespace, "courses", courses)

    return {}
