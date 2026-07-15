from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings used by the retrieval runtime."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    chroma_path: str = Field(default="./chroma_db", validation_alias="CHROMA_PATH")
    chroma_collection_name: str = Field(
        default="course_material_chunks_v1_1_cosine",
        validation_alias=AliasChoices("CHROMA_COLLECTION_NAME", "CHROMA_COLLECTION"),
    )
    embedding_model_name: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL_NAME", "EMBEDDING_MODEL"),
    )
    embedding_normalize: bool = Field(
        default=True,
        validation_alias="EMBEDDING_NORMALIZE",
    )
    embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=128,
        validation_alias="EMBEDDING_BATCH_SIZE",
    )
    embedding_validate_norms: bool = Field(
        default=False,
        validation_alias="EMBEDDING_VALIDATE_NORMS",
    )
    semantic_search_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices("SEMANTIC_SEARCH_TOP_K", "RAG_TOP_K"),
    )
    semantic_search_max_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        validation_alias="SEMANTIC_SEARCH_MAX_TOP_K",
    )
    semantic_search_min_similarity: float = Field(
        default=0.35,
        ge=-1.0,
        le=1.0,
        validation_alias="SEMANTIC_SEARCH_MIN_SIMILARITY",
    )
    semantic_search_max_query_length: int = Field(
        default=2000,
        ge=100,
        le=10000,
        validation_alias="SEMANTIC_SEARCH_MAX_QUERY_LENGTH",
    )
    semantic_search_max_candidates: int = Field(
        default=50,
        ge=1,
        le=200,
        validation_alias="SEMANTIC_SEARCH_MAX_CANDIDATES",
    )

    @field_validator("chroma_path", "chroma_collection_name", "embedding_model_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("配置值不能为空")
        return cleaned

    @model_validator(mode="after")
    def validate_retrieval_contract(self) -> "Settings":
        if not self.embedding_normalize:
            raise ValueError("1.1 cosine collection 要求 EMBEDDING_NORMALIZE=true")
        if self.semantic_search_top_k > self.semantic_search_max_top_k:
            raise ValueError("SEMANTIC_SEARCH_TOP_K 不能大于 SEMANTIC_SEARCH_MAX_TOP_K")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings for tests and controlled runtime reconfiguration."""

    get_settings.cache_clear()

