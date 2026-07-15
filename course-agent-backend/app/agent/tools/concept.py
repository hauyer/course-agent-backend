from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv

load_dotenv()


def _get_user_id(config: RunnableConfig) -> int:
    try:
        user_id = int((config or {}).get("configurable", {}).get("user_id"))
    except (ValueError, TypeError):
        raise ValueError("无法确定当前用户")
    if user_id < 1:
        raise ValueError("无法确定当前用户")
    return user_id


def _get_config_int(config: RunnableConfig, key: str, default: int) -> int:
    try:
        return int((config or {}).get("configurable", {}).get(key, default))
    except (ValueError, TypeError):
        return default


def _get_db():
    from app.database import SessionLocal
    return SessionLocal()


@tool
def explain_concept(concept_name: str, config: RunnableConfig) -> dict:
    """讲解编程或AI领域的概念。从已上传资料中语义检索相关内容，无资料时提示用户上传。"""
    from app.services.citation_service import (
        build_agent_citation_context,
        retrieve_course_chunks,
    )

    db = _get_db()
    try:
        user_id = _get_user_id(config)
        course_id = _get_config_int(config, "course_id", 0)
        if course_id < 1:
            raise ValueError("无法确定当前课程")
        citations = retrieve_course_chunks(
            db,
            user_id=user_id,
            course_id=course_id,
            query=concept_name,
            top_k=max(1, min(_get_config_int(config, "top_k", 5), 10)),
        )
        if not citations:
            return {
                "status": "no_evidence",
                "message": "当前课程资料中未检索到相似度足够高的内容。",
                "results": [],
            }
        return {
            "status": "success",
            "message": "已找到经过权限校验的课程资料片段。",
            "context": build_agent_citation_context(citations),
            "results": citations,
        }
    except Exception as exc:
        from app.services.course_retrieval_service import RetrievalUnavailableError

        if isinstance(exc, RetrievalUnavailableError):
            return {
                "status": "unavailable",
                "message": "课程资料检索服务暂不可用，请稍后重试。",
                "results": [],
            }
        return {
            "status": "no_evidence",
            "message": "当前课程资料中未检索到相似度足够高的内容。",
            "results": [],
        }
    finally:
        db.close()
