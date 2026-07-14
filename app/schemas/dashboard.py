from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_courses: int
    total_materials: int
    total_notes: int

    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    overdue_tasks: int

    today_tasks: int
    completed_today_tasks: int

    active_plans: int

    total_study_minutes: int
    today_study_minutes: int
    recent_days_minutes: int


class DashboardTaskItem(BaseModel):
    id: int
    course_id: Optional[int]
    course_name: Optional[str]

    title: str
    status: str
    priority: str

    due_at: Optional[datetime]
    estimated_minutes: Optional[int]

    is_overdue: bool


class DashboardPlanItem(BaseModel):
    id: int
    course_id: Optional[int]
    course_name: Optional[str]

    title: str
    start_date: date
    end_date: date
    daily_minutes: int
    status: str

    total_tasks: int
    completed_tasks: int
    progress_percent: float


class DashboardCourseItem(BaseModel):
    id: int
    name: str
    teacher: Optional[str]
    semester: Optional[str]

    material_count: int
    note_count: int

    total_tasks: int
    pending_tasks: int
    completed_tasks: int
    task_progress_percent: float

    course_progress_percent: int
    course_progress_status: str

    total_study_minutes: int


class DailyStudyPoint(BaseModel):
    date: date
    minutes: int


class DashboardOverviewResponse(BaseModel):
    generated_at: datetime
    trend_days: int

    summary: DashboardSummary

    today_task_items: list[DashboardTaskItem]
    upcoming_task_items: list[DashboardTaskItem]

    active_plan_items: list[DashboardPlanItem]
    course_items: list[DashboardCourseItem]

    study_trend: list[DailyStudyPoint]