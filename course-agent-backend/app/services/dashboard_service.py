from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_progress import CourseProgress
from app.models.learning_record import LearningRecord
from app.models.material import Material
from app.models.note import Note
from app.models.study_plan import StudyPlan
from app.models.study_plan_task import StudyPlanTask
from app.models.task import Task


ACTIVE_TASK_STATUSES = (
    "pending",
    "in_progress",
)


def _to_int(value: Any) -> int:
    """将数据库聚合结果安全转换为整数。"""
    return int(value or 0)


def _is_overdue(
    due_at: datetime | None,
    *,
    status: str,
    now: datetime,
) -> bool:
    if due_at is None:
        return False

    if status not in ACTIVE_TASK_STATUSES:
        return False

    # MySQL DATETIME 通常返回无时区 datetime
    if due_at.tzinfo is not None and now.tzinfo is None:
        due_at = due_at.replace(tzinfo=None)

    if due_at.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    return due_at < now


def _build_task_item(
    *,
    task: Task,
    course_name: str | None,
    now: datetime,
) -> dict:
    return {
        "id": task.id,
        "course_id": task.course_id,
        "course_name": course_name,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at,
        "estimated_minutes": task.estimated_minutes,
        "is_overdue": _is_overdue(
            task.due_at,
            status=task.status,
            now=now,
        ),
    }


def _get_study_minutes(
    db: Session,
    *,
    user_id: int,
    start_time: datetime | None = None,
    course_id: int | None = None,
) -> int:
    query = db.query(
        func.coalesce(
            func.sum(
                LearningRecord.duration_minutes
            ),
            0,
        )
    ).filter(
        LearningRecord.user_id == user_id
    )

    if start_time is not None:
        query = query.filter(
            LearningRecord.studied_at >= start_time
        )

    if course_id is not None:
        query = query.filter(
            LearningRecord.course_id == course_id
        )

    return _to_int(query.scalar())


def _get_plan_progress(
    db: Session,
    *,
    plan_id: int,
) -> tuple[int, int, float]:
    """
    返回计划中的有效任务数、完成任务数和完成百分比。

    cancelled 任务不计入总数。
    """
    base_query = (
        db.query(Task)
        .join(
            StudyPlanTask,
            StudyPlanTask.task_id == Task.id,
        )
        .filter(
            StudyPlanTask.study_plan_id == plan_id,
            Task.status != "cancelled",
        )
    )

    total_tasks = base_query.count()

    completed_tasks = base_query.filter(
        Task.status == "completed"
    ).count()

    if total_tasks == 0:
        progress_percent = 0.0
    else:
        progress_percent = round(
            completed_tasks / total_tasks * 100,
            2,
        )

    return (
        total_tasks,
        completed_tasks,
        progress_percent,
    )


def _get_study_trend(
    db: Session,
    *,
    user_id: int,
    trend_days: int,
    today: date,
) -> list[dict]:
    first_day = today - timedelta(
        days=trend_days - 1
    )

    first_datetime = datetime.combine(
        first_day,
        time.min,
    )

    rows = (
        db.query(
            func.date(
                LearningRecord.studied_at
            ).label("study_date"),
            func.coalesce(
                func.sum(
                    LearningRecord.duration_minutes
                ),
                0,
            ).label("minutes"),
        )
        .filter(
            LearningRecord.user_id == user_id,
            LearningRecord.studied_at
            >= first_datetime,
        )
        .group_by(
            func.date(
                LearningRecord.studied_at
            )
        )
        .all()
    )

    minutes_by_date: dict[date, int] = {}

    for study_date, minutes in rows:
        if isinstance(study_date, str):
            normalized_date = date.fromisoformat(
                study_date
            )
        elif isinstance(study_date, datetime):
            normalized_date = study_date.date()
        else:
            normalized_date = study_date

        minutes_by_date[normalized_date] = (
            _to_int(minutes)
        )

    return [
        {
            "date": first_day
            + timedelta(days=index),
            "minutes": minutes_by_date.get(
                first_day + timedelta(days=index),
                0,
            ),
        }
        for index in range(trend_days)
    ]


def get_dashboard_overview(
    db: Session,
    *,
    user_id: int,
    trend_days: int = 7,
    task_limit: int = 8,
    plan_limit: int = 5,
) -> dict:
    """
    聚合生成首页统计看板。

    此函数只读取已有业务表，不创建或修改数据。
    """
    # 使用运行后端电脑的本地时间计算今日范围
    now = datetime.now()
    today = now.date()

    today_start = datetime.combine(
        today,
        time.min,
    )

    tomorrow_start = today_start + timedelta(
        days=1
    )

    recent_start = today_start - timedelta(
        days=trend_days - 1
    )

    # ---------- 基础数量 ----------
    total_courses = _to_int(
        db.query(func.count(Course.id))
        .filter(
            Course.user_id == user_id
        )
        .scalar()
    )

    total_materials = _to_int(
        db.query(func.count(Material.id))
        .filter(
            Material.user_id == user_id
        )
        .scalar()
    )

    total_notes = _to_int(
        db.query(func.count(Note.id))
        .filter(
            Note.user_id == user_id
        )
        .scalar()
    )

    task_base = db.query(Task).filter(
        Task.user_id == user_id
    )

    total_tasks = task_base.count()

    pending_tasks = task_base.filter(
        Task.status == "pending"
    ).count()

    in_progress_tasks = task_base.filter(
        Task.status == "in_progress"
    ).count()

    completed_tasks = task_base.filter(
        Task.status == "completed"
    ).count()

    overdue_tasks = task_base.filter(
        Task.status.in_(ACTIVE_TASK_STATUSES),
        Task.due_at.isnot(None),
        Task.due_at < now,
    ).count()

    today_tasks = task_base.filter(
        Task.status.in_(ACTIVE_TASK_STATUSES),
        Task.due_at.isnot(None),
        Task.due_at >= today_start,
        Task.due_at < tomorrow_start,
    ).count()

    completed_today_tasks = task_base.filter(
        Task.status == "completed",
        Task.completed_at.isnot(None),
        Task.completed_at >= today_start,
        Task.completed_at < tomorrow_start,
    ).count()

    active_plans = (
        db.query(StudyPlan)
        .filter(
            StudyPlan.user_id == user_id,
            StudyPlan.status == "active",
        )
        .count()
    )

    total_study_minutes = _get_study_minutes(
        db,
        user_id=user_id,
    )

    today_study_minutes = _get_study_minutes(
        db,
        user_id=user_id,
        start_time=today_start,
    )

    recent_days_minutes = _get_study_minutes(
        db,
        user_id=user_id,
        start_time=recent_start,
    )

    summary = {
        "total_courses": total_courses,
        "total_materials": total_materials,
        "total_notes": total_notes,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        "today_tasks": today_tasks,
        "completed_today_tasks": (
            completed_today_tasks
        ),
        "active_plans": active_plans,
        "total_study_minutes": (
            total_study_minutes
        ),
        "today_study_minutes": (
            today_study_minutes
        ),
        "recent_days_minutes": (
            recent_days_minutes
        ),
    }

    # ---------- 今日任务 ----------
    today_task_rows = (
        db.query(
            Task,
            Course.name.label("course_name"),
        )
        .outerjoin(
            Course,
            Course.id == Task.course_id,
        )
        .filter(
            Task.user_id == user_id,
            Task.status.in_(
                ACTIVE_TASK_STATUSES
            ),
            Task.due_at.isnot(None),
            Task.due_at >= today_start,
            Task.due_at < tomorrow_start,
        )
        .order_by(
            Task.due_at.asc(),
            Task.priority.desc(),
            Task.id.asc(),
        )
        .limit(task_limit)
        .all()
    )

    today_task_items = [
        _build_task_item(
            task=task,
            course_name=course_name,
            now=now,
        )
        for task, course_name
        in today_task_rows
    ]

    # ---------- 后续任务 ----------
    upcoming_task_rows = (
        db.query(
            Task,
            Course.name.label("course_name"),
        )
        .outerjoin(
            Course,
            Course.id == Task.course_id,
        )
        .filter(
            Task.user_id == user_id,
            Task.status.in_(
                ACTIVE_TASK_STATUSES
            ),
            Task.due_at.isnot(None),
            Task.due_at >= tomorrow_start,
        )
        .order_by(
            Task.due_at.asc(),
            Task.id.asc(),
        )
        .limit(task_limit)
        .all()
    )

    upcoming_task_items = [
        _build_task_item(
            task=task,
            course_name=course_name,
            now=now,
        )
        for task, course_name
        in upcoming_task_rows
    ]

    # ---------- 活跃学习计划 ----------
    plan_rows = (
        db.query(
            StudyPlan,
            Course.name.label("course_name"),
        )
        .outerjoin(
            Course,
            Course.id == StudyPlan.course_id,
        )
        .filter(
            StudyPlan.user_id == user_id,
            StudyPlan.status == "active",
        )
        .order_by(
            StudyPlan.end_date.asc(),
            StudyPlan.id.asc(),
        )
        .limit(plan_limit)
        .all()
    )

    active_plan_items: list[dict] = []

    for plan, course_name in plan_rows:
        (
            plan_total_tasks,
            plan_completed_tasks,
            plan_progress_percent,
        ) = _get_plan_progress(
            db,
            plan_id=plan.id,
        )

        active_plan_items.append(
            {
                "id": plan.id,
                "course_id": plan.course_id,
                "course_name": course_name,
                "title": plan.title,
                "start_date": plan.start_date,
                "end_date": plan.end_date,
                "daily_minutes": (
                    plan.daily_minutes
                ),
                "status": plan.status,
                "total_tasks": (
                    plan_total_tasks
                ),
                "completed_tasks": (
                    plan_completed_tasks
                ),
                "progress_percent": (
                    plan_progress_percent
                ),
            }
        )

    # ---------- 各课程数据 ----------
    courses = (
        db.query(Course)
        .filter(
            Course.user_id == user_id
        )
        .order_by(
            Course.updated_at.desc(),
            Course.id.desc(),
        )
        .all()
    )

    course_items: list[dict] = []

    for course in courses:
        material_count = (
            db.query(Material)
            .filter(
                Material.user_id == user_id,
                Material.course_id == course.id,
            )
            .count()
        )

        note_count = (
            db.query(Note)
            .filter(
                Note.user_id == user_id,
                Note.course_id == course.id,
            )
            .count()
        )

        course_task_query = (
            db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.course_id == course.id,
                Task.status != "cancelled",
            )
        )

        course_total_tasks = (
            course_task_query.count()
        )

        course_pending_tasks = (
            course_task_query.filter(
                Task.status.in_(
                    ACTIVE_TASK_STATUSES
                )
            ).count()
        )

        course_completed_tasks = (
            course_task_query.filter(
                Task.status == "completed"
            ).count()
        )

        if course_total_tasks == 0:
            task_progress_percent = 0.0
        else:
            task_progress_percent = round(
                course_completed_tasks
                / course_total_tasks
                * 100,
                2,
            )

        progress = (
            db.query(CourseProgress)
            .filter(
                CourseProgress.user_id
                == user_id,
                CourseProgress.course_id
                == course.id,
            )
            .first()
        )

        if progress is None:
            course_progress_percent = 0
            course_progress_status = (
                "not_started"
            )
        else:
            course_progress_percent = (
                progress.progress_percent
            )
            course_progress_status = (
                progress.status
            )

        course_study_minutes = (
            _get_study_minutes(
                db,
                user_id=user_id,
                course_id=course.id,
            )
        )

        course_items.append(
            {
                "id": course.id,
                "name": course.name,
                "teacher": course.teacher,
                "semester": course.semester,
                "material_count": (
                    material_count
                ),
                "note_count": note_count,
                "total_tasks": (
                    course_total_tasks
                ),
                "pending_tasks": (
                    course_pending_tasks
                ),
                "completed_tasks": (
                    course_completed_tasks
                ),
                "task_progress_percent": (
                    task_progress_percent
                ),
                "course_progress_percent": (
                    course_progress_percent
                ),
                "course_progress_status": (
                    course_progress_status
                ),
                "total_study_minutes": (
                    course_study_minutes
                ),
            }
        )

    study_trend = _get_study_trend(
        db,
        user_id=user_id,
        trend_days=trend_days,
        today=today,
    )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ),
        "trend_days": trend_days,
        "summary": summary,
        "today_task_items": (
            today_task_items
        ),
        "upcoming_task_items": (
            upcoming_task_items
        ),
        "active_plan_items": (
            active_plan_items
        ),
        "course_items": course_items,
        "study_trend": study_trend,
    }