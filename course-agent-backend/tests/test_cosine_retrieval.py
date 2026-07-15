from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.citations import CitationCollector
from app.config import Settings
from app.database import Base
from app.models.course import Course
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.user import User
from app.services import citation_service, course_retrieval_service, vector_service
from app.services.course_retrieval_service import (
    CourseChunkSearchResult,
    RetrievalNotFoundError,
    cosine_similarity,
    distance_to_cosine_similarity,
    retrieve_course_chunks,
)


def retrieval_settings(**overrides):
    defaults = {
        "semantic_search_max_query_length": 2000,
        "semantic_search_max_top_k": 20,
        "semantic_search_min_similarity": 0.35,
        "semantic_search_max_candidates": 50,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeCollection:
    def __init__(self, raw=None, *, name="course_material_chunks_v1_1_cosine", space="cosine"):
        self.raw = raw or {"ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]]}
        self.name = name
        self.configuration = {"hnsw": {"space": space}}
        self.metadata = None
        self.queries = []
        self.deletes = []
        self.upserts = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return self.raw

    def delete(self, **kwargs):
        self.deletes.append(kwargs)

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class FakeClient:
    def __init__(self, collection):
        self.collection = collection
        self.calls = []

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return self.collection


@pytest.mark.parametrize(
    ("distance", "expected"),
    [(0.0, 1.0), (0.2, 0.8), (1.0, 0.0), (2.0, -1.0)],
)
def test_cosine_distance_conversion(distance, expected):
    assert distance_to_cosine_similarity(distance) == pytest.approx(expected)


def test_cosine_distance_conversion_clamps_float_noise():
    assert distance_to_cosine_similarity(-0.000001) == 1.0
    assert distance_to_cosine_similarity(2.000001) == -1.0
    assert distance_to_cosine_similarity(0.2) != pytest.approx(1 / 1.2)


def test_unit_vector_cosine_relationships():
    x = [1, 0]
    assert cosine_similarity(x, [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity(x, [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity(x, [-1, 0]) == pytest.approx(-1.0)


def test_settings_default_to_new_collection_and_require_normalization(monkeypatch):
    monkeypatch.delenv("CHROMA_COLLECTION_NAME", raising=False)
    monkeypatch.delenv("CHROMA_COLLECTION", raising=False)
    monkeypatch.delenv("EMBEDDING_NORMALIZE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.chroma_collection_name == "course_material_chunks_v1_1_cosine"
    assert settings.embedding_normalize is True
    with pytest.raises(ValueError, match="EMBEDDING_NORMALIZE"):
        Settings(_env_file=None, EMBEDDING_NORMALIZE=False)


def test_encode_texts_uses_normalized_batch_and_validates_output(monkeypatch):
    calls = []

    class FakeModel:
        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs))
            return np.asarray([[1.0, 0.0], [0.0, 1.0]])

    monkeypatch.setattr(vector_service, "get_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(
        vector_service,
        "get_settings",
        lambda: SimpleNamespace(embedding_batch_size=7, embedding_validate_norms=False),
    )
    result = vector_service.encode_texts(["alpha", "beta"], validate_norms=True)
    assert result == [[1.0, 0.0], [0.0, 1.0]]
    assert calls[0][1]["normalize_embeddings"] is True
    assert calls[0][1]["batch_size"] == 7
    with pytest.raises(ValueError, match="空字符串"):
        vector_service.encode_texts(["  "])


def test_encode_texts_rejects_non_finite_or_bad_dimensions(monkeypatch):
    class FakeModel:
        output = np.asarray([[1.0, float("nan")]])

        def encode(self, *_args, **_kwargs):
            return self.output

    model = FakeModel()
    monkeypatch.setattr(vector_service, "get_embedding_model", lambda: model)
    monkeypatch.setattr(
        vector_service,
        "get_settings",
        lambda: SimpleNamespace(embedding_batch_size=2, embedding_validate_norms=False),
    )
    with pytest.raises(vector_service.EmbeddingValidationError, match="NaN"):
        vector_service.encode_texts(["alpha"])
    model.output = [[1.0, 0.0], [1.0]]
    with pytest.raises(vector_service.EmbeddingValidationError, match="维度"):
        vector_service.encode_texts(["alpha", "beta"])


def test_collection_is_created_with_explicit_cosine_and_validated(monkeypatch):
    collection = FakeCollection()
    client = FakeClient(collection)
    vector_service.reset_vector_runtime_for_tests()
    monkeypatch.setattr(vector_service, "get_chroma_client", lambda: client)
    monkeypatch.setattr(
        vector_service,
        "get_settings",
        lambda: SimpleNamespace(chroma_collection_name="course_material_chunks_v1_1_cosine"),
    )
    assert vector_service.get_chroma_collection() is collection
    assert client.calls == [
        {
            "name": "course_material_chunks_v1_1_cosine",
            "configuration": {"hnsw": {"space": "cosine"}},
        }
    ]


def test_existing_wrong_metric_collection_is_rejected_without_modification(monkeypatch):
    collection = FakeCollection(space="l2")
    client = FakeClient(collection)
    vector_service.reset_vector_runtime_for_tests()
    monkeypatch.setattr(vector_service, "get_chroma_client", lambda: client)
    monkeypatch.setattr(
        vector_service,
        "get_settings",
        lambda: SimpleNamespace(chroma_collection_name="wrong_existing_collection"),
    )
    with pytest.raises(vector_service.CollectionMetricError, match="显式 cosine"):
        vector_service.get_chroma_collection()
    assert not hasattr(collection, "modify_calls")


@pytest.fixture
def search_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Course.__table__, Material.__table__, MaterialChunk.__table__],
    )
    db = sessionmaker(bind=engine)()
    alice = User(username="alice-r", email="alice-r@example.com", password_hash="x")
    bob = User(username="bob-r", email="bob-r@example.com", password_hash="x")
    db.add_all([alice, bob])
    db.flush()
    os_course = Course(user_id=alice.id, name="操作系统")
    db_course = Course(user_id=alice.id, name="数据库")
    foreign_course = Course(user_id=bob.id, name="他人课程")
    db.add_all([os_course, db_course, foreign_course])
    db.flush()

    def add(user, course, title, text, page=1):
        material = Material(
            user_id=user.id,
            course_id=course.id,
            title=title,
            original_filename=f"{title}.pdf",
            stored_filename=f"{user.id}-{course.id}-{title}.pdf",
            file_path=f"safe/{user.id}/{course.id}/{title}.pdf",
            file_type="pdf",
            file_size=len(text),
            parse_status="success",
        )
        db.add(material)
        db.flush()
        chunk = MaterialChunk(
            user_id=user.id,
            course_id=course.id,
            material_id=material.id,
            chunk_index=0,
            page_no=page,
            content=text,
            char_count=len(text),
            vector_status="success",
        )
        db.add(chunk)
        db.flush()
        return material, chunk

    owned_a = add(alice, os_course, "进程", "SQL 中的进程拥有独立地址空间。", None)
    owned_b = add(alice, os_course, "线程", "线程共享进程资源。", 2)
    cross = add(alice, db_course, "事务", "事务具有原子性。", 3)
    foreign = add(bob, foreign_course, "秘密", "其他用户资料。", 4)
    db.commit()
    yield db, alice, bob, os_course, db_course, owned_a, owned_b, cross, foreign
    db.close()


def metadata(user, course, material, chunk, **overrides):
    result = {
        "user_id": user.id,
        "course_id": course.id,
        "material_id": material.id,
        "chunk_id": chunk.id,
        "chunk_index": chunk.chunk_index,
        "page_no": chunk.page_no if chunk.page_no is not None else -1,
        "file_type": material.file_type,
    }
    result.update(overrides)
    return result


def install_retrieval_fakes(monkeypatch, collection):
    monkeypatch.setattr(course_retrieval_service, "get_settings", retrieval_settings)
    monkeypatch.setattr(course_retrieval_service, "encode_texts", lambda _texts: [[1.0, 0.0]])
    monkeypatch.setattr(course_retrieval_service, "get_chroma_collection", lambda: collection)


def test_retrieval_filters_threshold_deduplicates_and_uses_sql_content(monkeypatch, search_db):
    db, alice, _bob, course, _db_course, owned_a, owned_b, *_ = search_db
    material_a, chunk_a = owned_a
    material_b, chunk_b = owned_b
    collection = FakeCollection(
        {
            "ids": [["a", "a-duplicate", "b"]],
            "documents": [["untrusted", "untrusted duplicate", "untrusted low"]],
            "metadatas": [[
                metadata(alice, course, material_a, chunk_a),
                metadata(alice, course, material_a, chunk_a),
                metadata(alice, course, material_b, chunk_b),
            ]],
            "distances": [[0.1, 0.12, 0.8]],
        }
    )
    install_retrieval_fakes(monkeypatch, collection)
    results = retrieve_course_chunks(
        db,
        user_id=alice.id,
        course_id=course.id,
        query="  什么是进程  ",
        top_k=2,
        min_similarity=0.35,
    )
    assert [item.chunk_id for item in results] == [chunk_a.id]
    assert results[0].content == chunk_a.content
    assert results[0].content != "untrusted"
    assert results[0].similarity_score == pytest.approx(0.9)
    assert results[0].similarity_percent == 90.0
    assert results[0].page_no is None
    query = collection.queries[0]
    assert query["n_results"] == 6
    assert {"user_id": alice.id} in query["where"]["$and"]
    assert {"course_id": course.id} in query["where"]["$and"]


def test_retrieval_discards_poisoned_metadata_and_cross_scope_rows(monkeypatch, search_db):
    db, alice, bob, course, db_course, owned_a, _owned_b, cross, foreign = search_db
    owned_material, owned_chunk = owned_a
    cross_material, cross_chunk = cross
    foreign_material, foreign_chunk = foreign
    collection = FakeCollection(
        {
            "ids": [["poison-user", "cross-sql", "foreign-sql", "wrong-material"]],
            "documents": [["x", "x", "x", "x"]],
            "metadatas": [[
                metadata(alice, course, owned_material, owned_chunk, user_id=bob.id),
                metadata(alice, course, cross_material, cross_chunk, course_id=course.id),
                metadata(alice, course, foreign_material, foreign_chunk),
                metadata(alice, course, owned_material, owned_chunk, material_id=cross_material.id),
            ]],
            "distances": [[0.01, 0.02, 0.03, 0.04]],
        }
    )
    install_retrieval_fakes(monkeypatch, collection)
    assert retrieve_course_chunks(
        db,
        user_id=alice.id,
        course_id=course.id,
        query="权限",
        top_k=5,
    ) == []


def test_retrieval_rejects_foreign_course_and_material_filter(monkeypatch, search_db):
    db, alice, _bob, course, _db_course, _owned_a, _owned_b, _cross, foreign = search_db
    install_retrieval_fakes(monkeypatch, FakeCollection())
    foreign_material, _ = foreign
    with pytest.raises(RetrievalNotFoundError):
        retrieve_course_chunks(
            db,
            user_id=alice.id,
            course_id=foreign_material.course_id,
            query="越权",
        )
    with pytest.raises(RetrievalNotFoundError):
        retrieve_course_chunks(
            db,
            user_id=alice.id,
            course_id=course.id,
            query="注入",
            material_ids=[foreign_material.id],
        )


def test_retrieval_keeps_order_and_caps_top_k(monkeypatch, search_db):
    db, alice, _bob, course, _db_course, owned_a, owned_b, *_ = search_db
    items = [owned_b, owned_a]
    collection = FakeCollection(
        {
            "ids": [[f"chunk_{chunk.id}" for _material, chunk in items]],
            "documents": [["x", "x"]],
            "metadatas": [[metadata(alice, course, material, chunk) for material, chunk in items]],
            "distances": [[0.05, 0.1]],
        }
    )
    install_retrieval_fakes(monkeypatch, collection)
    results = retrieve_course_chunks(
        db, user_id=alice.id, course_id=course.id, query="排序", top_k=1
    )
    assert [item.chunk_id for item in results] == [items[0][1].id]


def test_citation_collector_uses_same_structured_result_and_no_low_evidence(monkeypatch):
    accepted = CourseChunkSearchResult(
        vector_id="chunk_7",
        chunk_id=7,
        chunk_index=2,
        course_id=1,
        course_name="操作系统",
        material_id=3,
        material_title="进程",
        file_type="pdf",
        page_no=12,
        content="进程拥有独立地址空间。",
        distance=0.2,
        similarity_score=0.8,
        similarity_percent=80.0,
    )
    monkeypatch.setattr(
        citation_service,
        "retrieve_structured_course_chunks",
        lambda *_args, **_kwargs: [accepted],
    )
    collector = CitationCollector()
    citations = citation_service.retrieve_course_chunks(
        object(), user_id=1, course_id=1, query="进程", top_k=5, collector=collector
    )
    assert citations[0]["chunk_id"] == accepted.chunk_id
    assert citations[0]["similarity_score"] == accepted.similarity_score
    assert citations[0]["citation_id"] == "C1"

    monkeypatch.setattr(
        citation_service,
        "retrieve_structured_course_chunks",
        lambda *_args, **_kwargs: [],
    )
    assert citation_service.retrieve_course_chunks(
        object(), user_id=1, course_id=1, query="无关", top_k=5
    ) == []


def test_strict_material_vector_delete_scope():
    collection = FakeCollection()
    vector_service.delete_material_vectors(
        user_id=4, course_id=5, material_id=6, collection=collection
    )
    assert collection.deletes == [
        {
            "where": {
                "$and": [{"user_id": 4}, {"course_id": 5}, {"material_id": 6}]
            }
        }
    ]
