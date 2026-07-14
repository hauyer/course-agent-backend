from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from sqlalchemy import Date, DateTime
from sqlalchemy.orm import Session

from app.models.agent_memory import AgentMemory
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.course import Course
from app.models.course_progress import CourseProgress
from app.models.learning_record import LearningRecord
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.note import Note
from app.models.study_plan import StudyPlan
from app.models.study_plan_task import StudyPlanTask
from app.models.task import Task


BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 10000


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(row) -> dict:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _rows(db: Session, model, *filters) -> list[dict]:
    return [_row(row) for row in db.query(model).filter(*filters).all()]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_user_backup(db: Session, *, user_id: int, upload_root: Path) -> Path:
    courses = db.query(Course).filter(Course.user_id == user_id).all()
    course_ids = [row.id for row in courses]
    materials = db.query(Material).filter(Material.user_id == user_id).all()
    material_ids = [row.id for row in materials]
    tasks = db.query(Task).filter(Task.user_id == user_id).all()
    task_ids = [row.id for row in tasks]
    plans = db.query(StudyPlan).filter(StudyPlan.user_id == user_id).all()
    plan_ids = [row.id for row in plans]
    notes = db.query(Note).filter(Note.user_id == user_id).all()
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).all()
    session_ids = [row.id for row in sessions]

    manifest = {
        "format": "course-study-desk-backup",
        "version": BACKUP_VERSION,
        "exported_at": datetime.now().astimezone().isoformat(),
        "security": {
            "contains_password": False,
            "contains_api_keys": False,
            "contains_integration_tokens": False,
        },
        "tables": {
            "courses": [_row(row) for row in courses],
            "materials": [_row(row) for row in materials],
            "material_chunks": _rows(db, MaterialChunk, MaterialChunk.user_id == user_id),
            "tasks": [_row(row) for row in tasks],
            "study_plans": [_row(row) for row in plans],
            "study_plan_tasks": _rows(db, StudyPlanTask, StudyPlanTask.study_plan_id.in_(plan_ids or [-1])),
            "notes": [_row(row) for row in notes],
            "chat_sessions": [_row(row) for row in sessions],
            "chat_messages": _rows(db, ChatMessage, ChatMessage.session_id.in_(session_ids or [-1])),
            "learning_records": _rows(db, LearningRecord, LearningRecord.user_id == user_id),
            "course_progresses": _rows(db, CourseProgress, CourseProgress.user_id == user_id),
            "agent_memories": _rows(db, AgentMemory, AgentMemory.user_id == user_id),
        },
        "files": [],
    }

    temp = NamedTemporaryFile(prefix="course-study-backup-", suffix=".zip", delete=False)
    temp.close()
    output = Path(temp.name)
    root = upload_root.resolve()
    try:
        with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for material in materials:
                source = Path(material.file_path).resolve()
                try:
                    source.relative_to(root)
                except ValueError:
                    continue
                if not source.is_file():
                    continue
                archive_path = f"files/{material.id}/{Path(material.stored_filename).name}"
                archive.write(source, archive_path)
                manifest["files"].append({
                    "material_id": material.id,
                    "archive_path": archive_path,
                    "size": source.stat().st_size,
                    "sha256": _sha256_file(source),
                })
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
            )
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise


def inspect_backup(path: Path) -> tuple[dict, ZipFile]:
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 512 MB")
    try:
        archive = ZipFile(path, "r")
    except BadZipFile as exc:
        raise ValueError("备份文件不是有效 ZIP") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        archive.close()
        raise ValueError("备份文件条目过多")
    if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise ValueError("备份解压后的数据超过安全限制")
    for item in infos:
        parts = PurePosixPath(item.filename).parts
        if item.filename.startswith(("/", "\\")) or ".." in parts:
            archive.close()
            raise ValueError("备份包含不安全路径")
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except Exception as exc:
        archive.close()
        raise ValueError("备份缺少有效 manifest.json") from exc
    if manifest.get("format") != "course-study-desk-backup" or manifest.get("version") != BACKUP_VERSION:
        archive.close()
        raise ValueError("备份格式或版本不受支持")
    return manifest, archive


def _convert(model, name: str, value):
    if value is None:
        return None
    column = model.__table__.columns.get(name)
    if column is None:
        return value
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date) and not isinstance(column.type, DateTime) and isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _create(db: Session, model, data: dict, *, overrides: dict, exclude: set[str] | None = None):
    excluded = {"id", *(exclude or set())}
    values = {
        column.name: _convert(model, column.name, data[column.name])
        for column in model.__table__.columns
        if column.name in data and column.name not in excluded
    }
    values.update(overrides)
    row = model(**values)
    db.add(row)
    db.flush()
    return row


def import_user_backup(
    db: Session,
    *,
    user_id: int,
    backup_path: Path,
    upload_root: Path,
) -> dict:
    manifest, archive = inspect_backup(backup_path)
    tables = manifest.get("tables") or {}
    written_files: list[Path] = []
    vector_material_ids: list[int] = []
    counts: dict[str, int] = {}
    try:
        course_map: dict[int, int] = {}
        for data in tables.get("courses", []):
            row = _create(db, Course, data, overrides={"user_id": user_id})
            course_map[int(data["id"])] = row.id
        counts["courses"] = len(course_map)

        file_index = {int(item["material_id"]): item for item in manifest.get("files", [])}
        material_map: dict[int, int] = {}
        for data in tables.get("materials", []):
            old_id = int(data["id"])
            old_course = int(data["course_id"])
            if old_course not in course_map:
                continue
            suffix = Path(str(data.get("stored_filename") or "")).suffix.lower()
            stored = f"{uuid4().hex}{suffix}"
            target_dir = upload_root / str(user_id) / str(course_map[old_course])
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / stored
            file_info = file_index.get(old_id)
            if file_info:
                digest = hashlib.sha256()
                copied_size = 0
                with archive.open(file_info["archive_path"]) as source, target.open("wb") as output:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(block)
                        digest.update(block)
                        copied_size += len(block)
                expected_size = int(file_info.get("size", copied_size))
                expected_hash = str(file_info.get("sha256") or "")
                if copied_size != expected_size or (expected_hash and not hmac.compare_digest(digest.hexdigest(), expected_hash)):
                    target.unlink(missing_ok=True)
                    raise ValueError(f"资料 {data.get('original_filename') or old_id} 校验失败")
                written_files.append(target)
            row = _create(
                db,
                Material,
                data,
                overrides={
                    "user_id": user_id,
                    "course_id": course_map[old_course],
                    "stored_filename": stored,
                    "file_path": target.as_posix(),
                },
            )
            material_map[old_id] = row.id
            vector_material_ids.append(row.id)
        counts["materials"] = len(material_map)

        chunk_count = 0
        for data in tables.get("material_chunks", []):
            old_material = int(data["material_id"])
            old_course = int(data["course_id"])
            if old_material not in material_map or old_course not in course_map:
                continue
            _create(
                db,
                MaterialChunk,
                data,
                overrides={
                    "user_id": user_id,
                    "course_id": course_map[old_course],
                    "material_id": material_map[old_material],
                    "vector_id": None,
                    "vector_status": "pending",
                },
            )
            chunk_count += 1
        counts["material_chunks"] = chunk_count

        task_map: dict[int, int] = {}
        task_rows: list[tuple[dict, Task]] = []
        for data in tables.get("tasks", []):
            old_course = data.get("course_id")
            row = _create(
                db,
                Task,
                data,
                overrides={
                    "user_id": user_id,
                    "course_id": course_map.get(int(old_course)) if old_course else None,
                    "parent_task_id": None,
                },
            )
            task_map[int(data["id"])] = row.id
            task_rows.append((data, row))
        for data, row in task_rows:
            parent = data.get("parent_task_id")
            row.parent_task_id = task_map.get(int(parent)) if parent else None
        counts["tasks"] = len(task_map)

        plan_map: dict[int, int] = {}
        for data in tables.get("study_plans", []):
            old_course = data.get("course_id")
            row = _create(
                db,
                StudyPlan,
                data,
                overrides={
                    "user_id": user_id,
                    "course_id": course_map.get(int(old_course)) if old_course else None,
                },
            )
            plan_map[int(data["id"])] = row.id
        counts["study_plans"] = len(plan_map)

        relation_count = 0
        for data in tables.get("study_plan_tasks", []):
            old_plan, old_task = int(data["study_plan_id"]), int(data["task_id"])
            if old_plan in plan_map and old_task in task_map:
                _create(db, StudyPlanTask, data, overrides={"study_plan_id": plan_map[old_plan], "task_id": task_map[old_task]})
                relation_count += 1
        counts["study_plan_tasks"] = relation_count

        note_map: dict[int, int] = {}
        for data in tables.get("notes", []):
            old_course = int(data["course_id"])
            if old_course not in course_map:
                continue
            row = _create(db, Note, data, overrides={"user_id": user_id, "course_id": course_map[old_course]})
            note_map[int(data["id"])] = row.id
        counts["notes"] = len(note_map)

        session_map: dict[int, int] = {}
        for data in tables.get("chat_sessions", []):
            old_course = int(data["course_id"])
            if old_course not in course_map:
                continue
            row = _create(db, ChatSession, data, overrides={"user_id": user_id, "course_id": course_map[old_course]})
            session_map[int(data["id"])] = row.id
        counts["chat_sessions"] = len(session_map)

        message_count = 0
        for data in tables.get("chat_messages", []):
            old_session = int(data["session_id"])
            if old_session in session_map:
                _create(db, ChatMessage, data, overrides={"session_id": session_map[old_session]})
                message_count += 1
        counts["chat_messages"] = message_count

        learning_count = 0
        for data in tables.get("learning_records", []):
            old_course = int(data["course_id"])
            if old_course not in course_map:
                continue
            old_material, old_task = data.get("material_id"), data.get("task_id")
            _create(
                db,
                LearningRecord,
                data,
                overrides={
                    "user_id": user_id,
                    "course_id": course_map[old_course],
                    "material_id": material_map.get(int(old_material)) if old_material else None,
                    "task_id": task_map.get(int(old_task)) if old_task else None,
                },
            )
            learning_count += 1
        counts["learning_records"] = learning_count

        progress_count = 0
        for data in tables.get("course_progresses", []):
            old_course = int(data["course_id"])
            if old_course in course_map:
                _create(db, CourseProgress, data, overrides={"user_id": user_id, "course_id": course_map[old_course]})
                progress_count += 1
        counts["course_progresses"] = progress_count

        memories = tables.get("agent_memories", [])
        if memories:
            current = db.query(AgentMemory).filter(AgentMemory.user_id == user_id).first()
            data = memories[0]
            if current:
                current.level = data.get("level") or current.level
                current.interests = list(dict.fromkeys([*(current.interests or []), *(data.get("interests") or [])]))
                current.courses = list(dict.fromkeys([*(current.courses or []), *(data.get("courses") or [])]))
            else:
                _create(db, AgentMemory, data, overrides={"user_id": user_id})
            counts["agent_memories"] = 1

        db.commit()
        return {"counts": counts, "vector_material_ids": vector_material_ids}
    except Exception:
        db.rollback()
        for file_path in written_files:
            file_path.unlink(missing_ok=True)
        raise
    finally:
        archive.close()
