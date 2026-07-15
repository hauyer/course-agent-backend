from typing import Optional

from pydantic import BaseModel, Field


class VectorIndexResponse(BaseModel):
    material_id: int
    indexed_count: int
    message: str


class SemanticSearchRequest(BaseModel):
    course_id: int

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20
    )

    min_similarity: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    material_ids: Optional[list[int]] = Field(default=None, max_length=50)
    file_types: Optional[list[str]] = Field(default=None, max_length=20)


class SemanticSearchItem(BaseModel):
    vector_id: str
    chunk_id: int
    chunk_index: int

    course_id: int
    course_name: str

    material_id: int
    material_title: str
    file_type: Optional[str] = None

    page_no: Optional[int] = None

    content: str
    distance: float
    similarity_score: float
    similarity_percent: float


class SemanticSearchResponse(BaseModel):
    course_id: int
    query: str
    metric: str = "cosine"
    min_similarity: float
    total: int
    results: list[SemanticSearchItem]
