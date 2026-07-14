from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.note import (
    NoteCreate,
    NoteListResponse,
    NoteResponse,
    NoteSyncRecordResponse,
    NoteUpdate,
    NotionSyncResponse,
    NotionTestResponse,
    ObsidianSyncResponse,
    ObsidianTestResponse,
)
from app.services.notion_service import (
    sync_note_to_notion,
    test_notion_connection,
)
from app.services.auth_service import (
    get_current_user,
)
from app.services.course_service import (
    get_course_by_id,
)
from app.services.note_service import (
    create_note,
    delete_note,
    get_note_by_id,
    list_note_sync_records,
    list_notes,
    update_note,
)
from app.services.obsidian_service import (
    sync_note_to_obsidian,
    test_obsidian_connection,
)


router = APIRouter()


def get_owned_course(
    *,
    db: Session,
    user_id: int,
    course_id: int,
):
    course = get_course_by_id(
        db=db,
        user_id=user_id,
        course_id=course_id,
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问",
        )

    return course


def get_owned_note(
    *,
    db: Session,
    user_id: int,
    note_id: int,
):
    note = get_note_by_id(
        db=db,
        user_id=user_id,
        note_id=note_id,
    )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="笔记不存在或无权限访问",
        )

    return note


# 静态路径放在 /{note_id} 之前
@router.post(
    "/integrations/obsidian/test",
    response_model=ObsidianTestResponse,
    summary="测试 Obsidian Vault 连接",
)
def test_obsidian_connection_api(
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        return test_obsidian_connection()

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

@router.post(
    "/integrations/notion/test",
    response_model=NotionTestResponse,
    summary="测试 Notion 连接",
)
def test_notion_connection_api(
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        return test_notion_connection()

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

@router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建课程笔记",
)
def create_note_api(
    note_in: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    get_owned_course(
        db=db,
        user_id=current_user.id,
        course_id=note_in.course_id,
    )

    try:
        return create_note(
            db=db,
            user_id=current_user.id,
            note_in=note_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=NoteListResponse,
    summary="查询课程笔记",
)
def list_notes_api(
    course_id: int | None = Query(
        default=None,
        ge=1,
    ),
    note_type: Literal[
        "manual",
        "summary",
        "knowledge_point",
        "review",
    ] | None = Query(default=None),
    keyword: str | None = Query(
        default=None,
        max_length=100,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    if course_id is not None:
        get_owned_course(
            db=db,
            user_id=current_user.id,
            course_id=course_id,
        )

    total, items = list_notes(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        note_type=note_type,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "items": items,
    }

@router.post(
    "/{note_id}/sync/notion",
    response_model=NotionSyncResponse,
    summary="将课程笔记同步到 Notion",
)
def sync_note_to_notion_api(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    note = get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )

    course = get_owned_course(
        db=db,
        user_id=current_user.id,
        course_id=note.course_id,
    )

    try:
        record = sync_note_to_notion(
            db=db,
            note=note,
            course=course,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "note_id": note.id,
        "provider": record.provider,
        "sync_status": record.sync_status,
        "notion_page_id": record.external_id,
        "page_url": record.external_path,
        "content_hash": record.content_hash,
        "last_synced_at": record.last_synced_at,
    }

@router.post(
    "/{note_id}/sync/obsidian",
    response_model=ObsidianSyncResponse,
    summary="将课程笔记同步到 Obsidian",
)
def sync_note_to_obsidian_api(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    note = get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )

    course = get_owned_course(
        db=db,
        user_id=current_user.id,
        course_id=note.course_id,
    )

    try:
        record = sync_note_to_obsidian(
            db=db,
            note=note,
            course=course,
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "note_id": note.id,
        "provider": record.provider,
        "sync_status": record.sync_status,
        "external_path": record.external_path,
        "content_hash": record.content_hash,
        "last_synced_at": record.last_synced_at,
    }


@router.get(
    "/{note_id}/sync-records",
    response_model=list[
        NoteSyncRecordResponse
    ],
    summary="查询笔记同步记录",
)
def get_note_sync_records_api(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    note = get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )

    return list_note_sync_records(
        db=db,
        note_id=note.id,
    )


@router.get(
    "/{note_id}",
    response_model=NoteResponse,
    summary="获取课程笔记详情",
)
def get_note_api(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    return get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )


@router.put(
    "/{note_id}",
    response_model=NoteResponse,
    summary="修改课程笔记",
)
def update_note_api(
    note_id: int,
    note_in: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    note = get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )

    update_data = note_in.model_dump(
        exclude_unset=True
    )

    if "course_id" in update_data:
        get_owned_course(
            db=db,
            user_id=current_user.id,
            course_id=update_data["course_id"],
        )

    try:
        return update_note(
            db=db,
            note=note,
            note_in=note_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{note_id}",
    summary="删除课程笔记",
)
def delete_note_api(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    note = get_owned_note(
        db=db,
        user_id=current_user.id,
        note_id=note_id,
    )

    delete_note(
        db=db,
        note=note,
    )

    return {
        "message": (
            "课程笔记删除成功；"
            "已同步到 Obsidian 的文件未自动删除"
        )
    }