import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.note import Note
from app.models.note_sync_record import NoteSyncRecord


load_dotenv()


INVALID_FILENAME_PATTERN = re.compile(
    r'[<>:"/\\|?*\x00-\x1F]'
)


def sanitize_filename(
    value: str,
    *,
    fallback: str,
    max_length: int = 100,
) -> str:
    """生成可安全用于 Windows 文件名的文本。"""
    cleaned = INVALID_FILENAME_PATTERN.sub(
        "_",
        value.strip(),
    )

    cleaned = cleaned.rstrip(". ")

    if not cleaned:
        cleaned = fallback

    return cleaned[:max_length]


def get_obsidian_vault_path() -> Path:
    """读取并验证 Obsidian Vault 路径。"""
    raw_path = os.getenv(
        "OBSIDIAN_VAULT_PATH"
    )

    if not raw_path:
        raise RuntimeError(
            "未配置 OBSIDIAN_VAULT_PATH"
        )

    vault_path = Path(
        raw_path
    ).expanduser().resolve()

    if not vault_path.exists():
        raise RuntimeError(
            f"Obsidian Vault 不存在：{vault_path}"
        )

    if not vault_path.is_dir():
        raise RuntimeError(
            f"Obsidian Vault 不是文件夹：{vault_path}"
        )

    return vault_path


def get_obsidian_base_folder() -> str:
    """读取 Vault 内的课程助手基础目录。"""
    raw_folder = os.getenv(
        "OBSIDIAN_BASE_FOLDER",
        "课程学习助手",
    )

    return sanitize_filename(
        raw_folder,
        fallback="课程学习助手",
    )


def ensure_path_inside_vault(
    *,
    vault_path: Path,
    target_path: Path,
) -> None:
    """防止路径穿越到 Vault 以外。"""
    resolved_vault = vault_path.resolve()
    resolved_target = target_path.resolve()

    if not resolved_target.is_relative_to(
        resolved_vault
    ):
        raise RuntimeError(
            "目标路径不在 Obsidian Vault 内"
        )


def yaml_string(value: str) -> str:
    """
    JSON 字符串同时是合法的 YAML 字符串，
    可以避免标题中引号等字符破坏 frontmatter。
    """
    return json.dumps(
        value,
        ensure_ascii=False,
    )


def build_obsidian_markdown(
    *,
    note: Note,
    course: Course,
) -> str:
    """生成包含 YAML frontmatter 的 Markdown。"""
    if note.tags:
        tags_text = "\n".join(
            f"  - {yaml_string(tag)}"
            for tag in note.tags
        )
        tags_section = f"tags:\n{tags_text}"
    else:
        tags_section = "tags: []"

    updated_at = (
        note.updated_at.isoformat()
        if note.updated_at is not None
        else datetime.now(
            timezone.utc
        ).isoformat()
    )

    content = note.content_markdown.strip()

    return (
        "---\n"
        f"course_agent_note_id: {note.id}\n"
        f"course_id: {note.course_id}\n"
        f"course: {yaml_string(course.name)}\n"
        f"note_type: {yaml_string(note.note_type)}\n"
        f"source: {yaml_string(note.source)}\n"
        f"updated_at: {yaml_string(updated_at)}\n"
        f"{tags_section}\n"
        "---\n\n"
        f"# {note.title}\n\n"
        f"{content}\n"
    )


def calculate_content_hash(
    content: str,
) -> str:
    """计算同步内容的 SHA-256。"""
    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def get_obsidian_sync_record(
    db: Session,
    *,
    note_id: int,
) -> NoteSyncRecord | None:
    return (
        db.query(NoteSyncRecord)
        .filter(
            NoteSyncRecord.note_id == note_id,
            NoteSyncRecord.provider
            == "obsidian",
        )
        .first()
    )


def save_failed_sync_record(
    db: Session,
    *,
    note_id: int,
    error_message: str,
) -> None:
    """记录同步失败，但不影响原笔记。"""
    record = get_obsidian_sync_record(
        db,
        note_id=note_id,
    )

    if record is None:
        record = NoteSyncRecord(
            note_id=note_id,
            provider="obsidian",
            sync_status="failed",
        )
        db.add(record)

    record.sync_status = "failed"
    record.last_error = error_message[:5000]

    try:
        db.commit()
    except Exception:
        db.rollback()


def test_obsidian_connection() -> dict:
    """测试 Vault 路径是否存在并且可写。"""
    vault_path = get_obsidian_vault_path()
    base_folder = get_obsidian_base_folder()

    target_folder = (
        vault_path / base_folder
    )

    ensure_path_inside_vault(
        vault_path=vault_path,
        target_path=target_folder,
    )

    target_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file = target_folder / (
        f".course_agent_test_"
        f"{uuid4().hex}.tmp"
    )

    try:
        test_file.write_text(
            "course-agent write test",
            encoding="utf-8",
        )

    except OSError as exc:
        raise RuntimeError(
            f"Obsidian Vault 无法写入：{exc}"
        ) from exc

    finally:
        if test_file.exists():
            test_file.unlink()

    return {
        "success": True,
        "vault_path": str(vault_path),
        "base_folder": base_folder,
        "message": "Obsidian Vault 连接测试成功",
    }


def sync_note_to_obsidian(
    db: Session,
    *,
    note: Note,
    course: Course,
) -> NoteSyncRecord:
    """将课程笔记写入 Obsidian Vault。"""
    temporary_path: Path | None = None

    try:
        vault_path = get_obsidian_vault_path()
        base_folder = get_obsidian_base_folder()

        record = get_obsidian_sync_record(
            db,
            note_id=note.id,
        )

        # 已经同步过时继续使用原路径，
        # 防止修改标题后生成重复文件。
        if (
            record is not None
            and record.external_path
        ):
            relative_path = Path(
                record.external_path
            )

        else:
            course_folder = sanitize_filename(
                course.name,
                fallback=f"课程_{course.id}",
            )

            note_filename = sanitize_filename(
                note.title,
                fallback=f"笔记_{note.id}",
            )

            relative_path = (
                Path(base_folder)
                / course_folder
                / f"{note.id:06d}-{note_filename}.md"
            )

        target_path = (
            vault_path / relative_path
        )

        ensure_path_inside_vault(
            vault_path=vault_path,
            target_path=target_path,
        )

        target_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        markdown_content = (
            build_obsidian_markdown(
                note=note,
                course=course,
            )
        )

        content_hash = calculate_content_hash(
            markdown_content
        )

        # 内容没有变化且文件存在时，
        # 不再重复覆盖磁盘。
        if (
            record is not None
            and record.content_hash
            == content_hash
            and target_path.exists()
        ):
            record.sync_status = "success"
            record.last_error = None
            record.last_synced_at = (
                datetime.now(timezone.utc)
            )

            db.commit()
            db.refresh(record)
            return record

        temporary_path = target_path.with_name(
            target_path.name
            + f".{uuid4().hex}.tmp"
        )

        temporary_path.write_text(
            markdown_content,
            encoding="utf-8",
        )

        # 同一磁盘内原子替换，避免写到一半中断
        os.replace(
            temporary_path,
            target_path,
        )

        if record is None:
            record = NoteSyncRecord(
                note_id=note.id,
                provider="obsidian",
            )
            db.add(record)

        record.external_path = (
            target_path
            .relative_to(vault_path)
            .as_posix()
        )

        record.external_id = None
        record.sync_status = "success"
        record.content_hash = content_hash
        record.last_synced_at = datetime.now(
            timezone.utc
        )
        record.last_error = None

        db.commit()
        db.refresh(record)

        return record

    except Exception as exc:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink(
                missing_ok=True
            )

        db.rollback()

        save_failed_sync_record(
            db,
            note_id=note.id,
            error_message=str(exc),
        )

        if isinstance(exc, RuntimeError):
            raise

        raise RuntimeError(
            f"同步到 Obsidian 失败：{exc}"
        ) from exc