from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv

load_dotenv()


def _get_user_id(config: RunnableConfig) -> int:
    try:
        return int(config.get("configurable", {}).get("user_id", 1))
    except (ValueError, TypeError):
        return 1


def _get_db():
    from app.database import SessionLocal
    return SessionLocal()


@tool
def explain_concept(concept_name: str, config: RunnableConfig) -> str:
    """讲解编程或AI领域的概念。从已上传资料中语义检索相关内容，无资料时提示用户上传。"""
    from app.models.material import Material
    from app.services.vector_service import encode_texts, get_chroma_collection

    db = _get_db()
    try:
        query_embedding = encode_texts([concept_name])
        if not query_embedding:
            return f"暂未收录'{concept_name}'的讲解，请上传相关资料后重试"

        collection = get_chroma_collection()
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=5,
            where={"user_id": _get_user_id(config)},
            include=["documents", "metadatas", "distances"],
        )

        result_ids = results.get("ids", [[]])[0] if results.get("ids") else []
        if not result_ids:
            return f"暂未收录'{concept_name}'的讲解，请上传相关资料后重试"

        documents = results.get("documents", [[]])[0] or []
        metadatas = results.get("metadatas", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []

        # 查询资料标题
        material_ids = {
            int(m["material_id"])
            for m in metadatas
            if m and "material_id" in m
        }
        materials = (
            db.query(Material).filter(Material.id.in_(material_ids)).all()
            if material_ids
            else []
        )
        material_map = {m.id: m for m in materials}

        lines = [f"从课程资料中检索到以下与'{concept_name}'相关的内容："]
        for i, vid in enumerate(result_ids):
            metadata = metadatas[i] or {}
            content = documents[i] or ""
            distance = float(distances[i])
            score = round(1.0 / (1.0 + max(distance, 0.0)), 4)

            mat_id = int(metadata.get("material_id", 0))
            mat = material_map.get(mat_id)
            source = f"《{mat.title}》" if mat else "未知资料"
            page_no = metadata.get("page_no")
            if page_no and page_no >= 0:
                source += f" 第{page_no}页"

            lines.append(f"[{source}] 相似度{score} {content[:300]}")

        return "\n".join(lines)
    except Exception:
        return f"暂未收录'{concept_name}'的讲解"
    finally:
        db.close()
