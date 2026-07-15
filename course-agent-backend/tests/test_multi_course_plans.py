from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.course import Course
from app.models.course_progress import CourseProgress
from app.models.study_plan import StudyPlan
from app.models.study_plan_course import StudyPlanCourse
from app.models.study_plan_task import StudyPlanTask
from app.models.task import Task
from app.models.user import User
from app.schemas.study_plan import MultiCoursePlanRequest
from app.services import multi_course_plan_service
from app.services.multi_course_plan_service import (
    MultiPlanConflictError,
    create_multi_course_plan,
    regenerate_multi_course_plan,
)
from app.services.multi_course_planner import (
    PlannerCourse,
    build_multi_course_schedule,
)


def planner_courses() -> list[PlannerCourse]:
    return [
        PlannerCourse(1, "操作系统", 5, date(2026, 7, 17), 180),
        PlannerCourse(2, "数据库", 2, date(2026, 7, 20), 180),
    ]


def test_planner_is_deterministic_and_never_exceeds_daily_capacity():
    kwargs = {
        "start_date": date(2026, 7, 15),
        "end_date": date(2026, 7, 20),
        "daily_minutes": 90,
        "available_weekdays": [1, 2, 3, 4, 5, 6, 7],
        "courses": planner_courses(),
    }
    first = build_multi_course_schedule(**kwargs)
    second = build_multi_course_schedule(**kwargs)

    assert first == second
    assert first["scheduled_minutes"] == 360
    assert first["unscheduled_minutes"] == 0
    assert all(day["total_minutes"] <= 90 for day in first["daily_schedule"])
    for day in first["daily_schedule"]:
        for task in day["tasks"]:
            course = next(item for item in planner_courses() if item.course_id == task["course_id"])
            assert task["planned_date"] <= course.deadline


def test_planner_prioritizes_urgent_and_high_priority_courses():
    result = build_multi_course_schedule(
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 15),
        daily_minutes=60,
        available_weekdays=[3],
        courses=planner_courses(),
    )
    summary = {item["course_id"]: item for item in result["course_summary"]}

    assert summary[1]["scheduled_minutes"] > summary[2]["scheduled_minutes"]
    assert result["unscheduled_minutes"] == 300
    assert any("缺少 300 分钟" in item for item in result["warnings"])


def test_planner_accounts_for_progress_and_existing_tasks():
    result = build_multi_course_schedule(
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 20),
        daily_minutes=120,
        available_weekdays=[1, 2, 3, 4, 5, 6, 7],
        courses=[
            PlannerCourse(1, "操作系统", 3, date(2026, 7, 20), 200, 25, 50),
            PlannerCourse(2, "数据库", 3, date(2026, 7, 20), 100, 0, 0),
        ],
    )
    summary = {item["course_id"]: item for item in result["course_summary"]}
    assert summary[1]["required_minutes"] == 100
    assert result["required_minutes"] == 200


@pytest.fixture
def plan_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Course.__table__,
            CourseProgress.__table__,
            StudyPlan.__table__,
            Task.__table__,
            StudyPlanTask.__table__,
            StudyPlanCourse.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    alice = User(username="alice-plan", email="alice-plan@example.com", password_hash="x")
    bob = User(username="bob-plan", email="bob-plan@example.com", password_hash="x")
    session.add_all([alice, bob])
    session.flush()
    os_course = Course(user_id=alice.id, name="操作系统")
    db_course = Course(user_id=alice.id, name="数据库")
    foreign_course = Course(user_id=bob.id, name="他人的课程")
    session.add_all([os_course, db_course, foreign_course])
    session.commit()
    try:
        yield session, alice, bob, os_course, db_course, foreign_course
    finally:
        session.close()
        engine.dispose()


def make_request(course_ids: list[int], request_id: str = "request-0001") -> MultiCoursePlanRequest:
    return MultiCoursePlanRequest(
        title="期末综合复习",
        goal="完成两门课程复习",
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 18),
        daily_minutes=100,
        available_weekdays=[1, 2, 3, 4, 5, 6, 7],
        courses=[
            {
                "course_id": course_ids[0],
                "priority": 5,
                "deadline": date(2026, 7, 17),
                "target_minutes": 180,
            },
            {
                "course_id": course_ids[1],
                "priority": 3,
                "deadline": date(2026, 7, 18),
                "target_minutes": 120,
            },
        ],
        client_request_id=request_id,
    )


def test_request_rejects_duplicate_courses():
    with pytest.raises(ValidationError, match="同一课程不能重复选择"):
        make_request([1, 1])


def test_create_multi_plan_writes_existing_task_models_and_is_idempotent(plan_db):
    db, alice, _, course_a, course_b, _ = plan_db
    request = make_request([course_a.id, course_b.id])

    first = create_multi_course_plan(db, user_id=alice.id, request=request)
    task_count = db.query(Task).filter(Task.user_id == alice.id).count()
    second = create_multi_course_plan(db, user_id=alice.id, request=request)

    assert first["created"] is True
    assert second["created"] is False
    assert second["plan"].id == first["plan"].id
    assert db.query(Task).filter(Task.user_id == alice.id).count() == task_count
    assert db.query(StudyPlanCourse).filter_by(study_plan_id=first["plan"].id).count() == 2
    tasks = db.query(Task).filter(Task.user_id == alice.id).all()
    assert tasks
    assert all(task.source == "study_plan" for task in tasks)
    assert all(task.due_at is not None and task.estimated_minutes for task in tasks)
    assert all(task.course_id in {course_a.id, course_b.id} for task in tasks)


def test_idempotency_key_rejects_different_payload(plan_db):
    db, alice, _, course_a, course_b, _ = plan_db
    request = make_request([course_a.id, course_b.id])
    create_multi_course_plan(db, user_id=alice.id, request=request)
    changed = request.model_copy(update={"daily_minutes": 120})

    with pytest.raises(MultiPlanConflictError):
        create_multi_course_plan(db, user_id=alice.id, request=changed)


def test_create_multi_plan_rejects_foreign_course(plan_db):
    db, alice, _, course_a, _, foreign_course = plan_db
    with pytest.raises(PermissionError):
        create_multi_course_plan(
            db,
            user_id=alice.id,
            request=make_request([course_a.id, foreign_course.id]),
        )


def test_create_multi_plan_rolls_back_every_table_on_failure(plan_db, monkeypatch):
    db, alice, _, course_a, course_b, _ = plan_db

    def fail_after_plan_flush(*_args, **_kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(multi_course_plan_service, "_add_generated_tasks", fail_after_plan_flush)
    with pytest.raises(RuntimeError, match="injected failure"):
        create_multi_course_plan(
            db,
            user_id=alice.id,
            request=make_request([course_a.id, course_b.id]),
        )

    assert db.query(StudyPlan).count() == 0
    assert db.query(StudyPlanCourse).count() == 0
    assert db.query(StudyPlanTask).count() == 0
    assert db.query(Task).count() == 0


def test_regeneration_preserves_completed_and_manual_tasks_and_uses_version(plan_db):
    db, alice, _, course_a, course_b, _ = plan_db
    created = create_multi_course_plan(
        db,
        user_id=alice.id,
        request=make_request([course_a.id, course_b.id]),
    )
    plan = created["plan"]
    generated = (
        db.query(Task)
        .join(StudyPlanTask, StudyPlanTask.task_id == Task.id)
        .filter(StudyPlanTask.study_plan_id == plan.id)
        .order_by(Task.id.asc())
        .all()
    )
    completed = generated[0]
    completed.status = "completed"
    manual = Task(
        user_id=alice.id,
        course_id=course_a.id,
        title="手工保留任务",
        status="pending",
        priority="medium",
        due_at=completed.due_at,
        estimated_minutes=30,
        source="manual",
    )
    db.add(manual)
    db.flush()
    db.add(
        StudyPlanTask(
            study_plan_id=plan.id,
            task_id=manual.id,
            planned_date=plan.start_date,
            sequence_no=999,
        )
    )
    db.commit()

    result = regenerate_multi_course_plan(
        db,
        user_id=alice.id,
        plan_id=plan.id,
        expected_version=1,
    )

    assert result["plan"].version == 2
    assert db.query(Task).filter(Task.id == completed.id).one().status == "completed"
    assert db.query(Task).filter(Task.id == manual.id).one().source == "manual"
    with pytest.raises(MultiPlanConflictError):
        regenerate_multi_course_plan(
            db,
            user_id=alice.id,
            plan_id=plan.id,
            expected_version=1,
        )


def test_deleting_multi_plan_cascades_only_its_links(plan_db):
    db, alice, _, course_a, course_b, _ = plan_db
    plan = create_multi_course_plan(
        db,
        user_id=alice.id,
        request=make_request([course_a.id, course_b.id]),
    )["plan"]
    db.delete(plan)
    db.commit()
    assert db.query(StudyPlanCourse).count() == 0
    assert db.query(StudyPlanTask).count() == 0
