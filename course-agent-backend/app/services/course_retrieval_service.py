from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.course import Course
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.services.vector_service import VectorServiceError, encode_texts, get_chroma_collection
from app.utils.file_parser import normalize_text


logger = logging.getLogger(__name__)
MAX_RESPONSE_CONTENT_LENGTH = 4000


class RetrievalError(RuntimeError):
    pass


class RetrievalValidationError(RetrievalError):
    pass


class RetrievalNotFoundError(RetrievalError):
    pass


class RetrievalUnavailableError(RetrievalError):
    pass


@dataclass(frozen=True, slots=True)
class CourseChunkSearchResult:
    vector_id: str
    chunk_id: int
    chunk_index: int
    course_id: int
    course_name: str
    material_id: int
    material_title: str
    file_type: str | None
    page_no: int | None
    content: str
    distance: float
    similarity_score: float
    similarity_percent: float

    def to_dict(self, *, content_limit: int | None = MAX_RESPONSE_CONTENT_LENGTH) -> dict[str, Any]:
        data = asdict(self)
        if content_limit is not None and len(data["content"]) > content_limit:
            data["content"] = data["content"][: content_limit - 1].rstrip() + "…"
        return data


def distance_to_cosine_similarity(distance: float) -> float:
    """Convert Chroma cosine distance to true cosine similarity."""

    return max(-1.0, min(1.0, 1.0 - float(distance)))


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Small deterministic helper used only for diagnostics and unit tests."""

    x = [float(value) for value in left]
    y = [float(value) for value in right]
    if len(x) != len(y) or not x:
        raise ValueError("向量必须非空且维度一致")
    dot = sum(a * b for a, b in zip(x, y))
    left_norm = sum(a * a for a in x) ** 0.5
    right_norm = sum(b * b for b in y) ** 0.5
    if left_norm == 0 or right_norm == 0:
        raise ValueError("零向量没有余弦相似度")
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _first_row(values: Any) -> list[Any]:
    if not values or not isinstance(values, (list, tuple)):
        return []
    first = values[0]
    return list(first) if isinstance(first, (list, tuple)) else []


def _build_where(
    *,
    user_id: int,
    course_id: int,
    material_ids: list[int] | None,
    file_types: list[str] | None,
) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [
        {"user_id": int(user_id)},
        {"course_id": int(course_id)},
    ]
    if material_ids:
        clauses.append({"material_id": {"$in": [int(item) for item in material_ids]}})
    if file_types:
        clauses.append({"file_type": {"$in": file_types}})
    return {"$and": clauses}


def retrieve_course_chunks(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    query: str,
    top_k: int = 5,
    min_similarity: float | None = None,
    material_ids: list[int] | None = None,
    file_types: list[str] | None = None,
) -> list[CourseChunkSearchResult]:
    """The only application entry point for course-scoped semantic search."""

    settings = get_settings()
    if user_id < 1 or course_id < 1:
        raise RetrievalValidationError("无法确定当前用户或课程")
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        raise RetrievalValidationError("检索问题不能为空")
    if len(cleaned_query) > settings.semantic_search_max_query_length:
        raise RetrievalValidationError("检索问题过长")
    if top_k < 1 or top_k > settings.semantic_search_max_top_k:
        raise RetrievalValidationError(
            f"top_k 必须在 1 到 {settings.semantic_search_max_top_k} 之间"
        )
    threshold = (
        settings.semantic_search_min_similarity
        if min_similarity is None
        else float(min_similarity)
    )
    if threshold < -1.0 or threshold > 1.0:
        raise RetrievalValidationError("min_similarity 必须在 -1 到 1 之间")

    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.user_id == user_id)
        .first()
    )
    if course is None:
        raise RetrievalNotFoundError("课程不存在或无权限访问")

    normalized_material_ids: list[int] | None = None
    if material_ids is not None:
        normalized_material_ids = list(dict.fromkeys(int(item) for item in material_ids))
        if not normalized_material_ids:
            return []
        owned_ids = {
            row[0]
            for row in (
                db.query(Material.id)
                .filter(
                    Material.id.in_(normalized_material_ids),
                    Material.user_id == user_id,
                    Material.course_id == course_id,
                )
                .all()
            )
        }
        if owned_ids != set(normalized_material_ids):
            raise RetrievalNotFoundError("资料不存在或无权限访问")

    normalized_file_types = None
    if file_types is not None:
        normalized_file_types = list(
            dict.fromkeys(value.strip().lower() for value in file_types if value.strip())
        )
        if not normalized_file_types:
            return []

    candidate_k = min(
        max(top_k * 3, top_k),
        settings.semantic_search_max_candidates,
    )
    try:
        query_embedding = encode_texts([cleaned_query])[0]
        collection = get_chroma_collection()
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_k,
            where=_build_where(
                user_id=user_id,
                course_id=course_id,
                material_ids=normalized_material_ids,
                file_types=normalized_file_types,
            ),
            include=["documents", "metadatas", "distances"],
        )
    except VectorServiceError as exc:
        raise RetrievalUnavailableError("语义检索服务暂不可用") from exc
    except Exception as exc:
        raise RetrievalUnavailableError("语义检索服务暂不可用") from exc

    ids = _first_row(raw.get("ids"))
    metadatas = _first_row(raw.get("metadatas"))
    distances = _first_row(raw.get("distances"))
    candidates: list[tuple[str, dict[str, Any], float]] = []
    ordered_chunk_ids: list[int] = []
    seen_candidate_ids: set[int] = set()
    for index, vector_id in enumerate(ids):
        if index >= len(metadatas) or index >= len(distances):
            continue
        metadata = metadatas[index] or {}
        try:
            chunk_id = int(metadata["chunk_id"])
            distance = float(distances[index])
            metadata_user_id = int(metadata["user_id"])
            metadata_course_id = int(metadata["course_id"])
            metadata_material_id = int(metadata["material_id"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Discarded malformed Chroma result for course_id=%s", course_id)
            continue
        if metadata_user_id != user_id or metadata_course_id != course_id:
            logger.warning("Discarded out-of-scope Chroma result for course_id=%s", course_id)
            continue
        if normalized_material_ids is not None and metadata_material_id not in normalized_material_ids:
            logger.warning("Discarded Chroma material outside requested filter")
            continue
        if chunk_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(chunk_id)
        ordered_chunk_ids.append(chunk_id)
        candidates.append((str(vector_id), metadata, distance))

    if not ordered_chunk_ids:
        return []

    rows = (
        db.query(MaterialChunk, Material)
        .join(Material, Material.id == MaterialChunk.material_id)
        .filter(
            MaterialChunk.id.in_(ordered_chunk_ids),
            MaterialChunk.user_id == user_id,
            MaterialChunk.course_id == course_id,
            Material.user_id == user_id,
            Material.course_id == course_id,
        )
        .all()
    )
    verified = {chunk.id: (chunk, material) for chunk, material in rows}
    output: list[CourseChunkSearchResult] = []
    for vector_id, metadata, distance in candidates:
        chunk_id = int(metadata["chunk_id"])
        pair = verified.get(chunk_id)
        if pair is None:
            logger.warning("Discarded Chroma result missing scoped SQL row")
            continue
        chunk, material = pair
        if (
            int(metadata["material_id"]) != material.id
            or chunk.material_id != material.id
            or int(metadata.get("chunk_index", chunk.chunk_index)) != chunk.chunk_index
        ):
            logger.warning("Discarded Chroma metadata inconsistent with SQL")
            continue
        if normalized_file_types is not None and (material.file_type or "").lower() not in normalized_file_types:
            continue
        similarity = distance_to_cosine_similarity(distance)
        if similarity < threshold:
            continue
        output.append(
            CourseChunkSearchResult(
                vector_id=vector_id,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                course_id=course.id,
                course_name=course.name,
                material_id=material.id,
                material_title=material.title,
                file_type=material.file_type,
                page_no=chunk.page_no,
                content=normalize_text(chunk.content or ""),
                distance=round(distance, 6),
                similarity_score=round(similarity, 6),
                similarity_percent=round(max(0.0, similarity) * 100.0, 2),
            )
        )
        if len(output) >= top_k:
            break
    return output

