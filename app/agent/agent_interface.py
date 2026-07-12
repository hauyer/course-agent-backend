from app.agent.agent_kernel.supervisor import build_supervisor
from langgraph.checkpoint.memory import InMemorySaver
from app.agent.agent_kernel.memory import store
from typing import AsyncIterator
from langchain_core.messages import HumanMessage


class AgentInterface:
    """后端调用 Agent 模块的唯一入口。"""

    def __init__(self):
        self.checkpointer=InMemorySaver()
        self.store=store
        self.graph=build_supervisor(checkpointer=self.checkpointer,store=self.store)

        # 初始化必要变量----------------------------------

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

        # ---------------------------------------------


    async def _run_stream(
            self,
            message:str,    #用户输入的字符串消息
            user_id:str,    #用户id
            thread_id:str   #用thread_id来隔离不同对话
    ) -> AsyncIterator[dict]:



        #初始化消息的输入state和配置config
        input_data={
            "messages":[HumanMessage(content=message)],
            "user_id":user_id,
        }

        config={"configurable":{"thread_id":thread_id,"user_id":user_id}}

        #输出逻辑
        async for event in self.graph.astream_events(input_data, config, version="v2"):
            kind = event["event"]

            # 用 metadata.langgraph_node 区分来源，不能用 event["name"]
            # （LLM 事件 name 始终是模型类名 "ChatDeepSeek"）
            node = event["metadata"].get("langgraph_node", "")

            if node in self._SKIP_NODES:
                continue

            # LLM 每吐一个 token，on_chat_model_stream 就触发一次 → 打字机效果
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield {"type": "token", "content": chunk.content}

            # 工具开始执行 → 通知用户 agent 在做什么
            elif kind == "on_tool_start":
                name = event["name"]
                yield {"type": "operation",
                       "name": self._TOOL_LABELS.get(name, name),
                       "detail": event["data"].get("input", {})}

            # 工具执行完毕 → 暴露结果，让用户看到 agent 的"思考依据"
            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if output:
                    content = output.content if hasattr(output, "content") else str(output)
                    yield {"type": "tool_result", "content": content}