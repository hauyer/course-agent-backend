from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.note import Note
from app.models.note_sync_record import NoteSyncRecord
from app.schemas.note import NoteCreate, NoteUpdate


def get_note_by_id(
    db: Session,
    *,
    user_id: int,
    note_id: int,
) -> Note | None:
    """查询当前用户拥有的笔记。"""
    return (
        db.query(Note)
        .filter(
            Note.id == note_id,
            Note.user_id == user_id,
        )
        .first()
    )


def create_note(
    db: Session,
    *,
    user_id: int,
    note_in: NoteCreate,
) -> Note:
    """创建课程笔记。"""
    title = note_in.title.strip()

    if not title:
        raise ValueError("笔记标题不能为空")

    note = Note(
        user_id=user_id,
        course_id=note_in.course_id,
        title=title,
        content_markdown=note_in.content_markdown,
        tags=note_in.tags,
        note_type=note_in.note_type,
        source=note_in.source,
    )

    db.add(note)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(note)
    return note


def list_notes(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
    note_type: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Note]]:
    """查询当前用户的课程笔记。"""
    query: Query = db.query(Note).filter(
        Note.user_id == user_id
    )

    if course_id is not None:
        query = query.filter(
            Note.course_id == course_id
        )

    if note_type is not None:
        query = query.filter(
            Note.note_type == note_type
        )

    if keyword:
        normalized = keyword.strip()

        if normalized:
            like_value = f"%{normalized}%"

            query = query.filter(
                or_(
                    Note.title.like(like_value),
                    Note.content_markdown.like(
                        like_value
                    ),
                )
            )

    total = query.count()

    items = (
        query.order_by(
            Note.updated_at.desc(),
            Note.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return total, items


def update_note(
    db: Session,
    *,
    note: Note,
    note_in: NoteUpdate,
) -> Note:
    """修改课程笔记。"""
    update_data = note_in.model_dump(
        exclude_unset=True
    )

    if "title" in update_data:
        title = update_data["title"]

        if title is None or not title.strip():
            raise ValueError("笔记标题不能为空")

        update_data["title"] = title.strip()

    for field_name, value in update_data.items():
        setattr(note, field_name, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(note)
    return note


def delete_note(
    db: Session,
    *,
    note: Note,
) -> None:
    """
    删除系统笔记。

    默认不删除已经同步到 Obsidian 的文件，
    防止误删用户本地笔记。
    """
    try:
        (
            db.query(NoteSyncRecord)
            .filter(
                NoteSyncRecord.note_id == note.id
            )
            .delete(
                synchronize_session=False
            )
        )

        db.delete(note)
        db.commit()

    except Exception:
        db.rollback()
        raise


def list_note_sync_records(
    db: Session,
    *,
    note_id: int,
) -> list[NoteSyncRecord]:
    """查询某篇笔记的同步记录。"""
    return (
        db.query(NoteSyncRecord)
        .filter(
            NoteSyncRecord.note_id == note_id
        )
        .order_by(
            NoteSyncRecord.updated_at.desc()
        )
        .all()
    )