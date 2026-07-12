from app.agent.agent_kernel.supervisor import build_supervisor
from langgraph.checkpoint.memory import InMemorySaver
from app.agent.agent_kernel.memory import store
from typing import AsyncIterator
from langchain_core.messages import HumanMessage


class AgentInterface:
    """后端调用 Agent 模块的唯一入口。"""

    # --- node → 前端展示映射说明 ---
    # 前端可根据 event["node"] 区分思考过程与最终输出。
    # 注意：astream_events 追踪子图内部节点名，不是 supervisor 包装名。
    #
    #   course_agent     → "🧠 课程助手思考中"    可折叠
    #   concept_agent    → "🧠 概念助手思考中"    可折叠
    #   material_agent   → "🧠 资料助手思考中"    可折叠
    #   plan_agent       → "🧠 规划师正在规划"    可折叠
    #   chat_agent       → 直接展示（非工具逻辑，无需折叠）
    #   tools            → 工具执行中（operation / tool_result）
    #   compress_node    → 系统消息（上下文已压缩） 静默或小字提示
    #
    # 规则：ReAct agent 的 token 流 = 思考过程，chat_agent 的 token 流 = 最终回答。

    def __init__(self):
        self.checkpointer = InMemorySaver()
        self.store = store
        self.graph = build_supervisor(checkpointer=self.checkpointer, store=self.store)

        # 内部节点：用户不需要看到它们产生的 token
        self._SKIP_NODES = {"supervisor_agent", "memory_node", "save_node"}

        # 工具名 → 用户可见的操作描述
        self._TOOL_LABELS = {
            "search_courses": "正在搜索课程",
            "list_all_courses": "正在列出全部课程",
            "create_course": "正在创建课程",
            "search_materials": "正在搜索学习资料",
            "add_material": "正在添加学习资料",
            "list_materials": "正在列出学习资料",
            "explain_concept": "正在查询知识库",
        }

    async def _run_stream(
        self,
        message: str,
        user_id: str,
        thread_id: str,
    ) -> AsyncIterator[dict]:
        """
        流式对话接口，返回异步迭代器供后端通过 SSE 推送给前端。

        ── 事件协议（前端请按此解析）──

        所有事件均包含以下公共字段：
            type   (str)  事件类型：token / operation / tool_result
            node   (str)  来源节点，用于区分思考过程与最终回答

        1. token — LLM 逐字输出（打字机效果）
            {
                "type": "token",
                "node": "course_agent_node",     # 来源节点
                "content": "Python基础课程..."    # 增量文本
            }
            前端判断：node 是 ReAct agent（*_agent_node 且非 chat_agent_node）
                     → 展示为"思考中"区域，建议可折叠
                     node 是 chat_agent_node
                     → 展示为最终回答区域

        2. operation — 工具开始执行
            {
                "type": "operation",
                "node": "tools",
                "name": "正在搜索课程",           # 中文操作名
                "detail": {"keyword": "python"}   # 工具入参
            }
            前端建议：展示为状态提示（如 loading 图标 + name）

        3. tool_result — 工具执行完毕
            {
                "type": "tool_result",
                "node": "tools",
                "content": "Python基础(20课时,李老师)..."  # 工具返回文本
            }
            前端建议：展示为可折叠引用块，标注"检索结果"

        4. 流结束 — 后端 SSE 在迭代器耗尽后自行追加
            {"type": "done"}
        """

        input_data = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
        }

        config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

        async for event in self.graph.astream_events(input_data, config, version="v2"):
            kind = event["event"]

            # metadata.langgraph_node 才是真正的图节点名
            # event["name"] 在 LLM 事件中是模型类名（如 "ChatDeepSeek"），不能用于区分来源
            node = event["metadata"].get("langgraph_node", "")

            if node in self._SKIP_NODES:
                continue

            # LLM 每吐一个 token，触发一次 on_chat_model_stream
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"type": "token", "content": chunk.content, "node": node}

            # 工具开始执行
            elif kind == "on_tool_start":
                name = event["name"]
                yield {
                    "type": "operation",
                    "name": self._TOOL_LABELS.get(name, name),
                    "detail": event["data"].get("input", {}),
                    "node": node,
                }

            # 工具执行完毕，结果作为 agent 的"思考依据"
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if output:
                    content = output.content if hasattr(output, "content") else str(output)
                    yield {"type": "tool_result", "content": content, "node": node}