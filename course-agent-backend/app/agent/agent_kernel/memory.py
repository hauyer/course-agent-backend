from langgraph.store.memory import InMemoryStore
from app.agent.agent_kernel.state import AgentState
from langchain_core.messages import SystemMessage,HumanMessage
from app.database import SessionLocal
from app.models.agent_memory import AgentMemory
from app.models.user import User

#only one store to manage memory
store=InMemoryStore()

MEMORY_PROMPT = "[长期记忆] 用户水平={level}，兴趣={interests}，已学={courses}"

DEFAULT_PROFILE = {
    "level": "beginner",
    "interests": [],
    "courses": [],
}


def _numeric_user_id(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_profile(user_id: int | None) -> dict:
    if user_id is None:
        return {**DEFAULT_PROFILE}
    db = SessionLocal()
    try:
        memory = db.query(AgentMemory).filter(AgentMemory.user_id == user_id).first()
        if memory is None:
            return {**DEFAULT_PROFILE}
        return {
            "level": memory.level or "beginner",
            "interests": list(memory.interests or []),
            "courses": list(memory.courses or []),
        }
    finally:
        db.close()

def memory_node(state:AgentState)->dict:
    #init user's memory or get memory of user

    uid = _numeric_user_id(state.get("user_id"))
    profile = _load_profile(uid)

    #return system prompt with long memory
    text=MEMORY_PROMPT.format(**profile)
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
    uid = _numeric_user_id(state.get("user_id"))
    if uid is None:
        return {}

    # 从本轮消息提取
    new_level     = _extract_level(state["messages"])
    new_interests = _extract_interests(state["messages"])
    new_courses   = _extract_courses(state["messages"])

    db = SessionLocal()
    try:
        # 锁住画像行，避免同一用户在多个会话并发更新时相互覆盖。
        memory = (
            db.query(AgentMemory)
            .filter(AgentMemory.user_id == uid)
            .with_for_update()
            .first()
        )
        if memory is None:
            if db.query(User.id).filter(User.id == uid).first() is None:
                return {}
            memory = AgentMemory(
                user_id=uid,
                level="beginner",
                interests=[],
                courses=[],
            )
            db.add(memory)

        ranks = {"beginner": 0, "intermediate": 1, "advanced": 2}
        if new_level and ranks.get(new_level, 0) > ranks.get(memory.level, 0):
            memory.level = new_level
        memory.interests = list(dict.fromkeys([*(memory.interests or []), *new_interests]))
        memory.courses = list(dict.fromkeys([*(memory.courses or []), *new_courses]))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {}
