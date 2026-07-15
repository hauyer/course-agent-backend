from datetime import date, datetime, time
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.task import TaskResponse


StudyPlanStatus = Literal[
    "draft",
    "active",
    "completed",
    "cancelled",
]

TaskPriority = Literal[
    "low",
    "medium",
    "high",
    "urgent",
]


class StudyPlanCreate(BaseModel):
    course_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    goal: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    start_date: date
    end_date: date

    daily_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
    )

    status: StudyPlanStatus = "draft"

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("计划结束日期不能早于开始日期")

        return self


class StudyPlanUpdate(BaseModel):
    course_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    goal: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    daily_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=1440,
    )

    status: Optional[StudyPlanStatus] = None


class StudyPlanStatusUpdate(BaseModel):
    status: StudyPlanStatus


class StudyPlanResponse(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int]

    title: str
    goal: Optional[str]

    start_date: date
    end_date: date
    daily_minutes: int
    status: str
    plan_type: str = "single"
    version: int = 1
    available_weekdays: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5, 6, 7]
    )

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudyPlanListResponse(BaseModel):
    total: int
    items: list[StudyPlanResponse]


class StudyPlanTaskCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    planned_date: date

    due_time: Optional[time] = Field(
        default=None,
        description="当天截止时间，不传时默认为 23:59:59",
    )

    sequence_no: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    priority: TaskPriority = "medium"

    estimated_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000,
    )

    parent_task_id: Optional[int] = Field(
        default=None,
        ge=1,
    )


class StudyPlanTaskResponse(BaseModel):
    id: int
    study_plan_id: int
    task_id: int
    planned_date: date
    sequence_no: int
    task: TaskResponse


class StudyPlanTaskListResponse(BaseModel):
    total: int
    items: list[StudyPlanTaskResponse]


class StudyPlanProgressResponse(BaseModel):
    study_plan_id: int

    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    cancelled_tasks: int
    overdue_tasks: int

    estimated_total_minutes: int
    completed_estimated_minutes: int

    progress_percent: float


class MultiCoursePlanCourseInput(BaseModel):
    course_id: int = Field(..., ge=1)
    priority: int = Field(..., ge=1, le=5)
    deadline: date
    target_minutes: int = Field(..., ge=20, le=100000)


class MultiCoursePlanRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    goal: Optional[str] = Field(default=None, max_length=5000)
    start_date: date
    end_date: date
    daily_minutes: int = Field(..., ge=15, le=720)
    available_weekdays: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5, 6, 7],
        min_length=1,
        max_length=7,
    )
    courses: list[MultiCoursePlanCourseInput] = Field(
        ...,
        min_length=2,
        max_length=10,
    )
    client_request_id: str = Field(..., min_length=8, max_length=64)

    @model_validator(mode="after")
    def validate_multi_plan(self):
        if self.end_date < self.start_date:
            raise ValueError("计划结束日期不能早于开始日期")
        if (self.end_date - self.start_date).days > 180:
            raise ValueError("综合规划跨度不能超过 180 天")
        if any(day < 1 or day > 7 for day in self.available_weekdays):
            raise ValueError("可学习星期必须位于 1 到 7")
        if len(set(self.available_weekdays)) != len(self.available_weekdays):
            raise ValueError("可学习星期不能重复")
        course_ids = [item.course_id for item in self.courses]
        if len(set(course_ids)) != len(course_ids):
            raise ValueError("同一课程不能重复选择")
        if any(item.deadline < self.start_date for item in self.courses):
            raise ValueError("课程截止日期不能早于计划开始日期")
        return self


class MultiCourseAllocationResponse(BaseModel):
    course_id: int
    course_name: str
    priority: int
    deadline: date
    target_minutes: int
    progress_percent: int
    existing_task_minutes: int
    required_minutes: int
    scheduled_minutes: int
    unscheduled_minutes: int
    weight: float


class MultiCourseScheduledTask(BaseModel):
    course_id: int
    course_name: str
    title: str
    description: str
    priority: TaskPriority
    estimated_minutes: int
    planned_date: date
    due_at: datetime


class MultiCourseDailySchedule(BaseModel):
    date: date
    total_minutes: int
    tasks: list[MultiCourseScheduledTask]
    course_summary: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MultiCoursePlanPreviewResponse(BaseModel):
    capacity_minutes: int
    required_minutes: int
    scheduled_minutes: int
    unscheduled_minutes: int
    warnings: list[str]
    daily_schedule: list[MultiCourseDailySchedule]
    course_summary: list[MultiCourseAllocationResponse]
    version: Optional[int] = None


class MultiCoursePlanCreateResponse(BaseModel):
    plan: StudyPlanResponse
    preview: MultiCoursePlanPreviewResponse
    created: bool


class MultiCoursePlanCourseResponse(BaseModel):
    id: int
    course_id: int
    course_name: str
    priority: int
    deadline: date
    target_minutes: int
    weight: float


class MultiCoursePlanCoursesResponse(BaseModel):
    total: int
    items: list[MultiCoursePlanCourseResponse]


class MultiCourseStoredTaskResponse(BaseModel):
    id: int
    course_id: int
    course_name: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    estimated_minutes: int
    due_at: Optional[datetime] = None
    source: str
    sequence_no: int


class MultiCourseStoredDailyScheduleResponse(BaseModel):
    date: date
    total_minutes: int
    tasks: list[MultiCourseStoredTaskResponse]
    course_summary: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MultiCourseRegenerateRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
