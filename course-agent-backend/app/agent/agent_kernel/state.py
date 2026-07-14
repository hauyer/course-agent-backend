from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    #node message
    # add_messages 支持按消息 ID 去重与 RemoveMessage，供上下文压缩真正替换
    # 旧消息；operator.add 只能追加，会让摘要与原历史同时留在状态中。
    messages:Annotated[list, add_messages]
    #next node/cover
    next:str
    #user id
    user_id:str
    #course id
    course_id:str
    # semantic retrieval result limit
    top_k:int
