import hashlib
import os
import re
from datetime import datetime, timezone
from uuid import UUID

import httpx
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.note import Note
from app.models.note_sync_record import NoteSyncRecord


load_dotenv()


NOTION_API_BASE = "https://api.notion.com/v1"
DEFAULT_NOTION_API_VERSION = "2026-03-11"


def normalize_notion_id(value: str) -> str:
    """
    支持以下格式：

    1. 32 位 Notion 页面 ID
    2. 带连字符的 UUID
    3. 完整 Notion 页面链接
    """
    if not value or not value.strip():
        raise RuntimeError("Notion 页面 ID 不能为空")

    matches = re.findall(
        (
            r"(?i)"
            r"([0-9a-f]{32}|"
            r"[0-9a-f]{8}-"
            r"[0-9a-f]{4}-"
            r"[0-9a-f]{4}-"
            r"[0-9a-f]{4}-"
            r"[0-9a-f]{12})"
        ),
        value.strip(),
    )

    if not matches:
        raise RuntimeError(
            "无法从 NOTION_PARENT_PAGE_ID 中识别 Notion 页面 ID"
        )

    compact_id = matches[-1].replace("-", "")

    try:
        return str(UUID(hex=compact_id))
    except ValueError as exc:
        raise RuntimeError("Notion 页面 ID 格式错误") from exc


def get_notion_config() -> tuple[str, str, str, float]:
    """读取并验证 Notion 配置。"""
    token = os.getenv("NOTION_API_KEY")

    if not token:
        raise RuntimeError(
            "未配置 NOTION_API_KEY，请先修改 .env"
        )

    raw_parent_id = os.getenv("NOTION_PARENT_PAGE_ID")

    if not raw_parent_id:
        raise RuntimeError(
            "未配置 NOTION_PARENT_PAGE_ID，请先修改 .env"
        )

    parent_page_id = normalize_notion_id(raw_parent_id)

    api_version = os.getenv(
        "NOTION_API_VERSION",
        DEFAULT_NOTION_API_VERSION,
    )

    try:
        timeout_seconds = float(
            os.getenv("NOTION_TIMEOUT_SECONDS", "30")
        )
    except ValueError as exc:
        raise RuntimeError(
            "NOTION_TIMEOUT_SECONDS 必须为数字"
        ) from exc

    return (
        token,
        parent_page_id,
        api_version,
        timeout_seconds,
    )


def build_notion_headers(
    *,
    token: str,
    api_version: str,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": api_version,
        "Content-Type": "application/json",
    }


def notion_request(
    method: str,
    path: str,
    *,
    json_data: dict | None = None,
) -> dict:
    """统一调用 Notion API 并转换错误信息。"""
    (
        token,
        _,
        api_version,
        timeout_seconds,
    ) = get_notion_config()

    url = f"{NOTION_API_BASE}{path}"

    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.request(
                method=method,
                url=url,
                headers=build_notion_headers(
                    token=token,
                    api_version=api_version,
                ),
                json=json_data,
            )

    except httpx.TimeoutException as exc:
        raise RuntimeError(
            "连接 Notion API 超时"
        ) from exc

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"无法连接 Notion API：{exc}"
        ) from exc

    if response.is_success:
        if not response.content:
            return {}

        return response.json()

    try:
        error_data = response.json()
        error_message = error_data.get(
            "message",
            response.text,
        )
    except ValueError:
        error_message = response.text

    if response.status_code == 401:
        raise RuntimeError(
            "Notion Token 无效，请检查 NOTION_API_KEY"
        )

    if response.status_code == 403:
        raise RuntimeError(
            "Notion Connection 权限不足，请检查 "
            "Read、Insert、Update content 权限"
        )

    if response.status_code == 404:
        raise RuntimeError(
            "Notion 页面不存在，或该页面尚未共享给 Connection"
        )

    if response.status_code == 429:
        raise RuntimeError(
            "Notion API 请求过于频繁，请稍后重试"
        )

    raise RuntimeError(
        f"Notion API 请求失败："
        f"HTTP {response.status_code}，{error_message}"
    )


def extract_page_title(page_data: dict) -> str:
    """从 Notion 页面返回数据中读取标题。"""
    properties = page_data.get("properties") or {}

    for property_data in properties.values():
        if property_data.get("type") != "title":
            continue

        title_items = property_data.get("title") or []

        title = "".join(
            item.get("plain_text", "")
            for item in title_items
        ).strip()

        if title:
            return title

    return "未命名 Notion 页面"


def test_notion_connection() -> dict:
    """验证 Token、父页面 ID 和页面访问权限。"""
    _, parent_page_id, _, _ = get_notion_config()

    page_data = notion_request(
        "GET",
        f"/pages/{parent_page_id}",
    )

    return {
        "success": True,
        "parent_page_id": parent_page_id,
        "parent_page_title": extract_page_title(
            page_data
        ),
        "message": "Notion 连接测试成功",
    }


def build_notion_markdown(
    *,
    note: Note,
    course: Course,
) -> str:
    """将系统课程笔记转换为 Notion Markdown 内容。"""
    tags_text = (
        "、".join(note.tags)
        if note.tags
        else "无"
    )

    updated_at = (
        note.updated_at.isoformat()
        if note.updated_at is not None
        else datetime.now(timezone.utc).isoformat()
    )

    content = note.content_markdown.strip()

    return (
        "> **来源：** 课程学习助手\n"
        f"> **课程：** {course.name}\n"
        f"> **笔记编号：** {note.id}\n"
        f"> **笔记类型：** {note.note_type}\n"
        f"> **标签：** {tags_text}\n"
        f"> **更新时间：** {updated_at}\n"
        "\n---\n\n"
        f"{content}\n"
    )


def calculate_content_hash(content: str) -> str:
    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def get_notion_sync_record(
    db: Session,
    *,
    note_id: int,
) -> NoteSyncRecord | None:
    return (
        db.query(NoteSyncRecord)
        .filter(
            NoteSyncRecord.note_id == note_id,
            NoteSyncRecord.provider == "notion",
        )
        .first()
    )


def save_failed_notion_sync(
    db: Session,
    *,
    note_id: int,
    error_message: str,
) -> None:
    """保存 Notion 同步失败记录。"""
    record = get_notion_sync_record(
        db,
        note_id=note_id,
    )

    if record is None:
        record = NoteSyncRecord(
            note_id=note_id,
            provider="notion",
            sync_status="failed",
        )
        db.add(record)

    record.sync_status = "failed"
    record.last_error = error_message[:5000]

    try:
        db.commit()
    except Exception:
        db.rollback()


def build_title_property(
    title: str,
) -> dict:
    return {
        "title": {
            "type": "title",
            "title": [
                {
                    "type": "text",
                    "text": {
                        "content": title[:2000]
                    },
                }
            ],
        }
    }


def create_notion_page(
    *,
    note: Note,
    markdown_content: str,
) -> dict:
    """首次同步时创建 Notion 子页面。"""
    _, parent_page_id, _, _ = get_notion_config()

    payload = {
        "parent": {
            "type": "page_id",
            "page_id": parent_page_id,
        },
        "properties": build_title_property(
            note.title
        ),
        "icon": {
            "type": "emoji",
            "emoji": "📘",
        },
        "markdown": markdown_content,
    }

    return notion_request(
        "POST",
        "/pages",
        json_data=payload,
    )


def update_notion_page_title(
    *,
    page_id: str,
    title: str,
) -> dict:
    """同步系统笔记标题到 Notion 页面标题。"""
    payload = {
        "properties": build_title_property(
            title
        )
    }

    return notion_request(
        "PATCH",
        f"/pages/{page_id}",
        json_data=payload,
    )


def replace_notion_page_content(
    *,
    page_id: str,
    markdown_content: str,
) -> dict:
    """使用 Markdown 完整替换 Notion 页面正文。"""
    payload = {
        "type": "replace_content",
        "replace_content": {
            "new_str": markdown_content,
        },
    }

    return notion_request(
        "PATCH",
        f"/pages/{page_id}/markdown",
        json_data=payload,
    )


def sync_note_to_notion(
    db: Session,
    *,
    note: Note,
    course: Course,
) -> NoteSyncRecord:
    """
    将系统笔记同步到 Notion。

    第一次同步创建页面；
    后续同步更新同一个页面。
    """
    try:
        markdown_content = build_notion_markdown(
            note=note,
            course=course,
        )

        content_hash = calculate_content_hash(
            markdown_content
        )

        record = get_notion_sync_record(
            db,
            note_id=note.id,
        )

        now = datetime.now(timezone.utc)

        if record is not None and record.external_id:
            page_id = normalize_notion_id(
                record.external_id
            )

            # 内容未变化时仍验证页面是否存在，
            # 但不重复更新正文。
            if record.content_hash == content_hash:
                page_data = notion_request(
                    "GET",
                    f"/pages/{page_id}",
                )

                page_url = (
                    page_data.get("url")
                    or record.external_path
                )

            else:
                page_data = update_notion_page_title(
                    page_id=page_id,
                    title=note.title,
                )

                replace_notion_page_content(
                    page_id=page_id,
                    markdown_content=markdown_content,
                )

                page_url = (
                    page_data.get("url")
                    or record.external_path
                )

        else:
            page_data = create_notion_page(
                note=note,
                markdown_content=markdown_content,
            )

            page_id = normalize_notion_id(
                page_data["id"]
            )

            page_url = page_data.get("url")

            if record is None:
                record = NoteSyncRecord(
                    note_id=note.id,
                    provider="notion",
                )
                db.add(record)

        record.external_id = page_id

        # 对 Notion 来说，external_path 保存页面 URL
        record.external_path = page_url

        record.sync_status = "success"
        record.content_hash = content_hash
        record.last_synced_at = now
        record.last_error = None

        db.commit()
        db.refresh(record)

        return record

    except Exception as exc:
        db.rollback()

        save_failed_notion_sync(
            db,
            note_id=note.id,
            error_message=str(exc),
        )

        if isinstance(exc, RuntimeError):
            raise

        raise RuntimeError(
            f"同步到 Notion 失败：{exc}"
        ) from exc