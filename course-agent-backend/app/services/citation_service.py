from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.citations import CitationCollector, get_citation_collector
from app.services.course_retrieval_service import (
    retrieve_course_chunks as retrieve_structured_course_chunks,
)


MAX_CITATION_CONTENT_LENGTH = 1000
_CITATION_MARKER = re.compile(r"\[C(\d+)\]")


def _safe_excerpt(content: str, limit: int = MAX_CITATION_CONTENT_LENGTH) -> str:
    normalized = " ".join((content or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def retrieve_course_chunks(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    query: str,
    top_k: int,
    min_similarity: float | None = None,
    collector: CitationCollector | None = None,
) -> list[dict[str, Any]]:
    """Register canonical retrieval results in the request-local collector."""

    results = retrieve_structured_course_chunks(
        db,
        user_id=user_id,
        course_id=course_id,
        query=query,
        top_k=top_k,
        min_similarity=min_similarity,
    )
    active_collector = collector or get_citation_collector()
    output: list[dict[str, Any]] = []
    for result in results:
        citation = {
            "course_id": result.course_id,
            "course_name": result.course_name,
            "material_id": result.material_id,
            "material_title": result.material_title,
            "file_type": result.file_type,
            "chunk_id": result.chunk_id,
            "chunk_index": result.chunk_index,
            "page_no": result.page_no,
            "content": _safe_excerpt(result.content),
            "distance": result.distance,
            "similarity_score": result.similarity_score,
            "similarity_percent": result.similarity_percent,
        }
        if active_collector is not None:
            citation = active_collector.register(citation)
        else:
            index = len(output) + 1
            citation = {**citation, "citation_id": f"C{index}", "index": index}
        output.append(citation)

    return output


def build_agent_citation_context(citations: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in citations:
        page = f"第 {item['page_no']} 页" if item.get("page_no") is not None else "页码未知"
        blocks.append(
            "\n".join(
                [
                    f"[{item['citation_id']}]",
                    f"课程：{item['course_name']}",
                    f"资料：{item['material_title']}",
                    f"位置：{page}，片段 {item['chunk_index']}",
                    f"余弦相似度：{float(item['similarity_score']):.4f}",
                    f"片段：{item['content']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def sanitize_answer_citation_markers(
    answer: str,
    citations: list[dict[str, Any]],
) -> str:
    valid_ids = {str(item["citation_id"]) for item in citations}

    def replace(match: re.Match[str]) -> str:
        marker = f"C{match.group(1)}"
        return match.group(0) if marker in valid_ids else ""

    return _CITATION_MARKER.sub(replace, answer).strip()
