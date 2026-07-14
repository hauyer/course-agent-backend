from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models.course import Course
from app.models.course_progress import CourseProgress
from app.models.learning_record import LearningRecord
from app.models.task import Task
from app.schemas.learning import (
    LearningRecordCreate,
    LearningRecordUpdate,
)


def get_learning_record_by_id(
    db: Session,
    *,
    user_id: int,
    record_id: int,
) -> LearningRecord | None:
    return (
        db.query(LearningRecord)
        .filter(
            LearningRecord.id == record_id,
            LearningRecord.user_id == user_id,
        )
        .first()
    )


def get_course_progress(
    db: Session,
    *,
    user_id: int,
    course_id: int,
) -> CourseProgress | None:
    return (
        db.query(CourseProgress)
        .filter(
            CourseProgress.user_id == user_id,
            CourseProgress.course_id == course_id,
        )
        .first()
    )


def _get_or_create_progress(
    db: Session,
    *,
    user_id: int,
    course_id: int,
) -> CourseProgress:
    progress = get_course_progress(
        db=db,
        user_id=user_id,
        course_id=course_id,
    )

    if progress is None:
        progress = CourseProgress(
            user_id=user_id,
            course_id=course_id,
            progress_percent=0,
            status="not_started",
        )
        db.add(progress)
        db.flush()

    return progress


def create_learning_record(
    db: Session,
    *,
    user_id: int,
    record_in: LearningRecordCreate,
) -> LearningRecord:
    record = LearningRecord(
        user_id=user_id,
        course_id=record_in.course_id,
        material_id=record_in.material_id,
        task_id=record_in.task_id,
        studied_at=record_in.studied_at,
        duration_minutes=record_in.duration_minutes,
        source=record_in.source,
        content_summary=record_in.content_summary,
        reflection=record_in.reflection,
    )

    progress = _get_or_create_progress(
        db=db,
        user_id=user_id,
        course_id=record_in.course_id,
    )

    if progress.started_at is None:
        progress.started_at = record_in.studied_at

    progress.last_studied_at = record_in.studied_at

    if progress.status == "not_started":
        progress.status = "in_progress"

    db.add(record)
    db.add(progress)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(record)
    return record


def list_learning_records(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LearningRecord]]:
    query: Query = db.query(LearningRecord).filter(
        LearningRecord.user_id == user_id
    )

    if course_id is not None:
        query = query.filter(
            LearningRecord.course_id == course_id
        )

    if start_time is not None:
        query = query.filter(
            LearningRecord.studied_at >= start_time
        )

    if end_time is not None:
        query = query.filter(
            LearningRecord.studied_at <= end_time
        )

    total = query.count()

    items = (
        query.order_by(
            LearningRecord.studied_at.desc(),
            LearningRecord.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return total, items


def update_learning_record(
    db: Session,
    *,
    record: LearningRecord,
    record_in: LearningRecordUpdate,
) -> LearningRecord:
    update_data = record_in.model_dump(
        exclude_unset=True
    )

    for field_name, value in update_data.items():
        setattr(record, field_name, value)

    db.flush()

    latest_studied_at = (
        db.query(
            func.max(LearningRecord.studied_at)
        )
        .filter(
            LearningRecord.user_id == record.user_id,
            LearningRecord.course_id == record.course_id,
        )
        .scalar()
    )

    progress = _get_or_create_progress(
        db=db,
        user_id=record.user_id,
        course_id=record.course_id,
    )

    progress.last_studied_at = latest_studied_at

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(record)
    return record


def delete_learning_record(
    db: Session,
    *,
    record: LearningRecord,
) -> None:
    user_id = record.user_id
    course_id = record.course_id

    try:
        db.delete(record)
        db.flush()

        latest_studied_at = (
            db.query(
                func.max(LearningRecord.studied_at)
            )
            .filter(
                LearningRecord.user_id == user_id,
                LearningRecord.course_id == course_id,
            )
            .scalar()
        )

        progress = get_course_progress(
            db=db,
            user_id=user_id,
            course_id=course_id,
        )

        if progress is not None:
            progress.last_studied_at = (
                latest_studied_at
            )

        db.commit()

    except Exception:
        db.rollback()
        raise


def update_course_progress(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    progress_percent: int,
    status: str | None,
) -> CourseProgress:
    progress = _get_or_create_progress(
        db=db,
        user_id=user_id,
        course_id=course_id,
    )

    now = datetime.now(timezone.utc)

    if status == "completed":
        progress_percent = 100

    if progress_percent == 100:
        actual_status = "completed"
    elif status is not None:
        actual_status = status
    elif progress_percent == 0:
        actual_status = "not_started"
    else:
        actual_status = "in_progress"

    progress.progress_percent = progress_percent
    progress.status = actual_status

    if (
        progress_percent > 0
        and progress.started_at is None
    ):
        progress.started_at = now

    if actual_status == "completed":
        progress.completed_at = now
    else:
        progress.completed_at = None

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(progress)
    return progress


def get_course_progress_detail(
    db: Session,
    *,
    user_id: int,
    course_id: int,
) -> dict:
    progress = get_course_progress(
        db=db,
        user_id=user_id,
        course_id=course_id,
    )

    record_query = db.query(
        func.count(LearningRecord.id),
        func.coalesce(
            func.sum(
                LearningRecord.duration_minutes
            ),
            0,
        ),
    ).filter(
        LearningRecord.user_id == user_id,
        LearningRecord.course_id == course_id,
    )

    record_count, total_minutes = (
        record_query.one()
    )

    task_query = db.query(Task).filter(
        Task.user_id == user_id,
        Task.course_id == course_id,
        Task.status != "cancelled",
    )

    total_tasks = task_query.count()

    completed_tasks = task_query.filter(
        Task.status == "completed"
    ).count()

    if total_tasks == 0:
        task_progress_percent = 0.0
    else:
        task_progress_percent = round(
            completed_tasks / total_tasks * 100,
            2,
        )

    if progress is None:
        return {
            "id": None,
            "course_id": course_id,
            "progress_percent": 0,
            "status": "not_started",
            "started_at": None,
            "last_studied_at": None,
            "completed_at": None,
            "total_study_minutes": int(
                total_minutes
            ),
            "learning_record_count": int(
                record_count
            ),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "task_progress_percent": (
                task_progress_percent
            ),
        }

    return {
        "id": progress.id,
        "course_id": course_id,
        "progress_percent": (
            progress.progress_percent
        ),
        "status": progress.status,
        "started_at": progress.started_at,
        "last_studied_at": (
            progress.last_studied_at
        ),
        "completed_at": progress.completed_at,
        "total_study_minutes": int(
            total_minutes
        ),
        "learning_record_count": int(
            record_count
        ),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "task_progress_percent": (
            task_progress_percent
        ),
    }


def get_learning_summary(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
) -> dict:
    now = datetime.now(timezone.utc)

    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    recent_start = today_start - timedelta(
        days=6
    )

    record_query: Query = db.query(
        LearningRecord
    ).filter(
        LearningRecord.user_id == user_id
    )

    task_query: Query = db.query(Task).filter(
        Task.user_id == user_id
    )

    if course_id is not None:
        record_query = record_query.filter(
            LearningRecord.course_id == course_id
        )

        task_query = task_query.filter(
            Task.course_id == course_id
        )

    total_study_minutes = (
        record_query.with_entities(
            func.coalesce(
                func.sum(
                    LearningRecord.duration_minutes
                ),
                0,
            )
        ).scalar()
        or 0
    )

    today_study_minutes = (
        record_query.filter(
            LearningRecord.studied_at
            >= today_start
        )
        .with_entities(
            func.coalesce(
                func.sum(
                    LearningRecord.duration_minutes
                ),
                0,
            )
        )
        .scalar()
        or 0
    )

    recent_7_days_minutes = (
        record_query.filter(
            LearningRecord.studied_at
            >= recent_start
        )
        .with_entities(
            func.coalesce(
                func.sum(
                    LearningRecord.duration_minutes
                ),
                0,
            )
        )
        .scalar()
        or 0
    )

    learning_record_count = (
        record_query.count()
    )

    effective_task_query = task_query.filter(
        Task.status != "cancelled"
    )

    total_tasks = effective_task_query.count()

    completed_tasks = (
        effective_task_query.filter(
            Task.status == "completed"
        ).count()
    )

    pending_tasks = (
        effective_task_query.filter(
            Task.status.in_(
                ["pending", "in_progress"]
            )
        ).count()
    )

    overdue_tasks = (
        effective_task_query.filter(
            Task.status.in_(
                ["pending", "in_progress"]
            ),
            Task.due_at.isnot(None),
            Task.due_at < now,
        ).count()
    )

    course_query: Query = db.query(Course).filter(
        Course.user_id == user_id
    )

    total_courses = course_query.count()

    progress_query: Query = db.query(
        CourseProgress
    ).filter(
        CourseProgress.user_id == user_id
    )

    active_courses = progress_query.filter(
        CourseProgress.status == "in_progress"
    ).count()

    completed_courses = progress_query.filter(
        CourseProgress.status == "completed"
    ).count()

    return {
        "course_id": course_id,
        "total_study_minutes": int(
            total_study_minutes
        ),
        "today_study_minutes": int(
            today_study_minutes
        ),
        "recent_7_days_minutes": int(
            recent_7_days_minutes
        ),
        "learning_record_count": (
            learning_record_count
        ),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "overdue_tasks": overdue_tasks,
        "total_courses": total_courses,
        "active_courses": active_courses,
        "completed_courses": completed_courses,
    }