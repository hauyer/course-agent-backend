from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.material import Material
from app.models.task import Task
from app.models.user import User
from app.schemas.learning import (
    CourseProgressResponse,
    CourseProgressUpdate,
    LearningRecordCreate,
    LearningRecordListResponse,
    LearningRecordResponse,
    LearningRecordUpdate,
    LearningSummaryResponse,
)
from app.services.auth_service import (
    get_current_user,
)
from app.services.course_service import (
    get_course_by_id,
)
from app.services.learning_service import (
    create_learning_record,
    delete_learning_record,
    get_course_progress_detail,
    get_learning_record_by_id,
    get_learning_summary,
    list_learning_records,
    update_course_progress,
    update_learning_record,
)


router = APIRouter()


def _get_owned_course(
    db: Session,
    *,
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


def _validate_related_objects(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    material_id: int | None,
    task_id: int | None,
) -> None:
    if material_id is not None:
        material = (
            db.query(Material)
            .filter(
                Material.id == material_id,
                Material.user_id == user_id,
                Material.course_id == course_id,
            )
            .first()
        )

        if material is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资料不存在或不属于当前课程",
            )

    if task_id is not None:
        task = (
            db.query(Task)
            .filter(
                Task.id == task_id,
                Task.user_id == user_id,
                Task.course_id == course_id,
            )
            .first()
        )

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在或不属于当前课程",
            )


@router.post(
    "/records",
    response_model=LearningRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增学习记录",
)
def create_learning_record_api(
    record_in: LearningRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    _get_owned_course(
        db,
        user_id=current_user.id,
        course_id=record_in.course_id,
    )

    _validate_related_objects(
        db,
        user_id=current_user.id,
        course_id=record_in.course_id,
        material_id=record_in.material_id,
        task_id=record_in.task_id,
    )

    return create_learning_record(
        db=db,
        user_id=current_user.id,
        record_in=record_in,
    )


@router.get(
    "/records",
    response_model=LearningRecordListResponse,
    summary="查询学习记录",
)
def list_learning_records_api(
    course_id: int | None = Query(
        default=None,
        ge=1,
    ),
    start_time: datetime | None = Query(
        default=None
    ),
    end_time: datetime | None = Query(
        default=None
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
        _get_owned_course(
            db,
            user_id=current_user.id,
            course_id=course_id,
        )

    total, items = list_learning_records(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "items": items,
    }


@router.get(
    "/summary",
    response_model=LearningSummaryResponse,
    summary="获取学习数据汇总",
)
def get_learning_summary_api(
    course_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    if course_id is not None:
        _get_owned_course(
            db,
            user_id=current_user.id,
            course_id=course_id,
        )

    return get_learning_summary(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
    )


@router.get(
    "/records/{record_id}",
    response_model=LearningRecordResponse,
    summary="获取学习记录详情",
)
def get_learning_record_api(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    record = get_learning_record_by_id(
        db=db,
        user_id=current_user.id,
        record_id=record_id,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学习记录不存在或无权限访问",
        )

    return record


@router.put(
    "/records/{record_id}",
    response_model=LearningRecordResponse,
    summary="修改学习记录",
)
def update_learning_record_api(
    record_id: int,
    record_in: LearningRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    record = get_learning_record_by_id(
        db=db,
        user_id=current_user.id,
        record_id=record_id,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学习记录不存在或无权限访问",
        )

    update_data = record_in.model_dump(
        exclude_unset=True
    )

    _validate_related_objects(
        db,
        user_id=current_user.id,
        course_id=record.course_id,
        material_id=update_data.get(
            "material_id"
        ),
        task_id=update_data.get("task_id"),
    )

    return update_learning_record(
        db=db,
        record=record,
        record_in=record_in,
    )


@router.delete(
    "/records/{record_id}",
    summary="删除学习记录",
)
def delete_learning_record_api(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    record = get_learning_record_by_id(
        db=db,
        user_id=current_user.id,
        record_id=record_id,
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学习记录不存在或无权限访问",
        )

    delete_learning_record(
        db=db,
        record=record,
    )

    return {
        "message": "学习记录删除成功"
    }


@router.get(
    "/courses/{course_id}/progress",
    response_model=CourseProgressResponse,
    summary="查询课程学习进度",
)
def get_course_progress_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    _get_owned_course(
        db,
        user_id=current_user.id,
        course_id=course_id,
    )

    return get_course_progress_detail(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
    )


@router.put(
    "/courses/{course_id}/progress",
    response_model=CourseProgressResponse,
    summary="更新课程学习进度",
)
def update_course_progress_api(
    course_id: int,
    progress_in: CourseProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    _get_owned_course(
        db,
        user_id=current_user.id,
        course_id=course_id,
    )

    update_course_progress(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        progress_percent=(
            progress_in.progress_percent
        ),
        status=progress_in.status,
    )

    return get_course_progress_detail(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
    )