from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_progress import CourseProgress
from app.models.study_plan import StudyPlan
from app.models.study_plan_course import StudyPlanCourse
from app.models.study_plan_task import StudyPlanTask
from app.models.task import Task
from app.schemas.study_plan import MultiCoursePlanRequest
from app.services.multi_course_planner import PlannerCourse, build_multi_course_schedule


class MultiPlanConflictError(ValueError):
    pass


def _request_matches_existing_plan(
    db: Session,
    *,
    user_id: int,
    plan: StudyPlan,
    request: MultiCoursePlanRequest,
) -> bool:
    """Prevent one idempotency key from confirming two different plans."""

    links = get_multi_plan_courses(db, user_id=user_id, plan_id=plan.id)
    expected_courses = sorted(
        (
            item.course_id,
            item.priority,
            item.deadline,
            item.target_minutes,
        )
        for item in request.courses
    )
    stored_courses = sorted(
        (
            item["course_id"],
            item["priority"],
            item["deadline"],
            item["target_minutes"],
        )
        for item in links
    )
    return (
        plan.plan_type == "multi"
        and plan.title == request.title.strip()
        and (plan.goal or None) == (request.goal or None)
        and plan.start_date == request.start_date
        and plan.end_date == request.end_date
        and plan.daily_minutes == request.daily_minutes
        and sorted(plan.available_weekdays or [])
        == sorted(request.available_weekdays)
        and stored_courses == expected_courses
    )


def _owned_course_map(
    db: Session,
    *,
    user_id: int,
    course_ids: list[int],
) -> dict[int, Course]:
    rows = (
        db.query(Course)
        .filter(Course.user_id == user_id, Course.id.in_(course_ids))
        .all()
    )
    result = {row.id: row for row in rows}
    if len(result) != len(set(course_ids)):
        raise PermissionError("课程不存在或无权限访问")
    return result


def _existing_task_minutes(
    db: Session,
    *,
    user_id: int,
    course_ids: list[int],
    exclude_plan_id: int | None,
) -> dict[int, int]:
    excluded_ids: list[int] = []
    completed_by_course: dict[int, int] = defaultdict(int)
    if exclude_plan_id is not None:
        plan_rows = (
            db.query(Task)
            .join(StudyPlanTask, StudyPlanTask.task_id == Task.id)
            .filter(
                StudyPlanTask.study_plan_id == exclude_plan_id,
                Task.user_id == user_id,
                Task.source == "study_plan",
            )
            .all()
        )
        excluded_ids = [row.id for row in plan_rows if row.status != "completed"]
        for row in plan_rows:
            if row.status == "completed" and row.course_id in course_ids:
                completed_by_course[row.course_id] += row.estimated_minutes or 0

    query = db.query(Task).filter(
        Task.user_id == user_id,
        Task.course_id.in_(course_ids),
        Task.status.in_(("pending", "in_progress")),
    )
    if excluded_ids:
        query = query.filter(~Task.id.in_(excluded_ids))
    totals: dict[int, int] = defaultdict(int)
    for row in query.all():
        totals[row.course_id] += row.estimated_minutes or 0
    for course_id, minutes in completed_by_course.items():
        totals[course_id] += minutes
    return totals


def preview_multi_course_plan(
    db: Session,
    *,
    user_id: int,
    request: MultiCoursePlanRequest,
    exclude_plan_id: int | None = None,
) -> dict[str, Any]:
    course_ids = [item.course_id for item in request.courses]
    courses = _owned_course_map(db, user_id=user_id, course_ids=course_ids)
    progress_rows = (
        db.query(CourseProgress)
        .filter(
            CourseProgress.user_id == user_id,
            CourseProgress.course_id.in_(course_ids),
        )
        .all()
    )
    progress = {row.course_id: row.progress_percent for row in progress_rows}
    existing = _existing_task_minutes(
        db,
        user_id=user_id,
        course_ids=course_ids,
        exclude_plan_id=exclude_plan_id,
    )
    planner_courses = [
        PlannerCourse(
            course_id=item.course_id,
            course_name=courses[item.course_id].name,
            priority=item.priority,
            deadline=item.deadline,
            target_minutes=item.target_minutes,
            progress_percent=progress.get(item.course_id, 0),
            existing_task_minutes=existing.get(item.course_id, 0),
        )
        for item in request.courses
    ]
    return build_multi_course_schedule(
        start_date=request.start_date,
        end_date=request.end_date,
        daily_minutes=request.daily_minutes,
        available_weekdays=request.available_weekdays,
        courses=planner_courses,
    )


def _add_generated_tasks(
    db: Session,
    *,
    plan: StudyPlan,
    user_id: int,
    preview: dict[str, Any],
) -> None:
    for day in preview["daily_schedule"]:
        for sequence_no, scheduled in enumerate(day["tasks"], start=1):
            task = Task(
                user_id=user_id,
                course_id=scheduled["course_id"],
                title=scheduled["title"],
                description=scheduled["description"],
                status="pending",
                priority=scheduled["priority"],
                due_at=scheduled["due_at"],
                estimated_minutes=scheduled["estimated_minutes"],
                source="study_plan",
            )
            db.add(task)
            db.flush()
            db.add(
                StudyPlanTask(
                    study_plan_id=plan.id,
                    task_id=task.id,
                    planned_date=scheduled["planned_date"],
                    sequence_no=sequence_no,
                )
            )


def create_multi_course_plan(
    db: Session,
    *,
    user_id: int,
    request: MultiCoursePlanRequest,
) -> dict[str, Any]:
    existing = (
        db.query(StudyPlan)
        .filter(
            StudyPlan.user_id == user_id,
            StudyPlan.client_request_id == request.client_request_id,
        )
        .first()
    )
    if existing is not None:
        if not _request_matches_existing_plan(
            db,
            user_id=user_id,
            plan=existing,
            request=request,
        ):
            raise MultiPlanConflictError("请求幂等键已被不同的计划内容使用")
        preview = preview_multi_plan_regeneration(
            db,
            user_id=user_id,
            plan=existing,
        )
        preview["version"] = existing.version
        return {"plan": existing, "preview": preview, "created": False}

    preview = preview_multi_course_plan(db, user_id=user_id, request=request)
    summary_map = {item["course_id"]: item for item in preview["course_summary"]}
    plan = StudyPlan(
        user_id=user_id,
        course_id=None,
        title=request.title.strip(),
        goal=request.goal,
        start_date=request.start_date,
        end_date=request.end_date,
        daily_minutes=request.daily_minutes,
        available_weekdays=sorted(request.available_weekdays),
        status="active",
        plan_type="multi",
        version=1,
        client_request_id=request.client_request_id,
    )
    try:
        db.add(plan)
        db.flush()
        for item in request.courses:
            db.add(
                StudyPlanCourse(
                    study_plan_id=plan.id,
                    user_id=user_id,
                    course_id=item.course_id,
                    priority=item.priority,
                    deadline=item.deadline,
                    target_minutes=item.target_minutes,
                    weight=summary_map[item.course_id]["weight"],
                )
            )
        _add_generated_tasks(db, plan=plan, user_id=user_id, preview=preview)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    preview["version"] = plan.version
    return {"plan": plan, "preview": preview, "created": True}


def get_multi_plan_courses(
    db: Session,
    *,
    user_id: int,
    plan_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(StudyPlanCourse, Course)
        .join(Course, Course.id == StudyPlanCourse.course_id)
        .filter(
            StudyPlanCourse.study_plan_id == plan_id,
            StudyPlanCourse.user_id == user_id,
            Course.user_id == user_id,
        )
        .order_by(StudyPlanCourse.priority.desc(), StudyPlanCourse.course_id.asc())
        .all()
    )
    return [
        {
            "id": link.id,
            "course_id": link.course_id,
            "course_name": course.name,
            "priority": link.priority,
            "deadline": link.deadline,
            "target_minutes": link.target_minutes,
            "weight": link.weight,
        }
        for link, course in rows
    ]


def get_multi_plan_schedule(
    db: Session,
    *,
    user_id: int,
    plan_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(StudyPlanTask, Task, Course)
        .join(Task, Task.id == StudyPlanTask.task_id)
        .join(Course, Course.id == Task.course_id)
        .filter(
            StudyPlanTask.study_plan_id == plan_id,
            Task.user_id == user_id,
            Course.user_id == user_id,
        )
        .order_by(
            StudyPlanTask.planned_date.asc(),
            StudyPlanTask.sequence_no.asc(),
            StudyPlanTask.id.asc(),
        )
        .all()
    )
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for link, task, course in rows:
        grouped[link.planned_date].append(
            {
                "id": task.id,
                "course_id": task.course_id,
                "course_name": course.name,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "estimated_minutes": task.estimated_minutes or 0,
                "due_at": task.due_at,
                "source": task.source,
                "sequence_no": link.sequence_no,
            }
        )
    result: list[dict[str, Any]] = []
    for planned_date, tasks in grouped.items():
        course_totals: dict[tuple[int, str], int] = defaultdict(int)
        for task in tasks:
            course_totals[(task["course_id"], task["course_name"])] += task["estimated_minutes"]
        result.append(
            {
                "date": planned_date,
                "total_minutes": sum(task["estimated_minutes"] for task in tasks),
                "tasks": tasks,
                "course_summary": [
                    {"course_id": key[0], "course_name": key[1], "minutes": minutes}
                    for key, minutes in sorted(course_totals.items())
                ],
                "warnings": [],
            }
        )
    return result


def _request_from_plan(db: Session, *, user_id: int, plan: StudyPlan) -> MultiCoursePlanRequest:
    courses = get_multi_plan_courses(db, user_id=user_id, plan_id=plan.id)
    if len(courses) < 2:
        raise ValueError("综合规划课程配置不完整")
    return MultiCoursePlanRequest(
        title=plan.title,
        goal=plan.goal,
        start_date=plan.start_date,
        end_date=plan.end_date,
        daily_minutes=plan.daily_minutes,
        available_weekdays=plan.available_weekdays or [1, 2, 3, 4, 5, 6, 7],
        courses=[
            {
                "course_id": item["course_id"],
                "priority": item["priority"],
                "deadline": item["deadline"],
                "target_minutes": item["target_minutes"],
            }
            for item in courses
        ],
        client_request_id=f"regenerate-{plan.id}-{plan.version}",
    )


def preview_multi_plan_regeneration(
    db: Session,
    *,
    user_id: int,
    plan: StudyPlan,
) -> dict[str, Any]:
    if plan.plan_type != "multi":
        raise ValueError("只有综合规划可以重新生成")
    request = _request_from_plan(db, user_id=user_id, plan=plan)
    preview = preview_multi_course_plan(
        db,
        user_id=user_id,
        request=request,
        exclude_plan_id=plan.id,
    )
    preview["version"] = plan.version
    return preview


def regenerate_multi_course_plan(
    db: Session,
    *,
    user_id: int,
    plan_id: int,
    expected_version: int,
) -> dict[str, Any]:
    plan = (
        db.query(StudyPlan)
        .filter(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
        .with_for_update()
        .first()
    )
    if plan is None:
        raise PermissionError("学习计划不存在或无权限访问")
    if plan.plan_type != "multi":
        raise ValueError("只有综合规划可以重新生成")
    if plan.version != expected_version:
        raise MultiPlanConflictError("计划已发生变化，请刷新预览后重试")

    preview = preview_multi_plan_regeneration(db, user_id=user_id, plan=plan)
    rows = (
        db.query(StudyPlanTask, Task)
        .join(Task, Task.id == StudyPlanTask.task_id)
        .filter(
            StudyPlanTask.study_plan_id == plan.id,
            Task.user_id == user_id,
            Task.source == "study_plan",
            Task.status != "completed",
        )
        .all()
    )
    try:
        for link, task in rows:
            db.delete(link)
            db.delete(task)
        db.flush()
        _add_generated_tasks(db, plan=plan, user_id=user_id, preview=preview)
        plan.version += 1
        db.add(plan)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    preview["version"] = plan.version
    return {"plan": plan, "preview": preview, "created": True}
