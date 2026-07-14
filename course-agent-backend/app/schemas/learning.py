from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


LearningSource = Literal[
    "manual",
    "material",
    "task",
    "study_plan",
]

ProgressStatus = Literal[
    "not_started",
    "in_progress",
    "paused",
    "completed",
]


class LearningRecordCreate(BaseModel):
    course_id: int = Field(..., ge=1)

    material_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    task_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    studied_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    duration_minutes: int = Field(
        ...,
        ge=1,
        le=1440,
    )

    source: LearningSource = "manual"

    content_summary: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    reflection: Optional[str] = Field(
        default=None,
        max_length=5000,
    )


class LearningRecordUpdate(BaseModel):
    material_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    task_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    studied_at: Optional[datetime] = None

    duration_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=1440,
    )

    source: Optional[LearningSource] = None

    content_summary: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    reflection: Optional[str] = Field(
        default=None,
        max_length=5000,
    )


class LearningRecordResponse(BaseModel):
    id: int
    user_id: int
    course_id: int

    material_id: Optional[int]
    task_id: Optional[int]

    studied_at: datetime
    duration_minutes: int
    source: str

    content_summary: Optional[str]
    reflection: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class LearningRecordListResponse(BaseModel):
    total: int
    items: list[LearningRecordResponse]


class CourseProgressUpdate(BaseModel):
    progress_percent: int = Field(
        ...,
        ge=0,
        le=100,
    )

    status: Optional[ProgressStatus] = None


class CourseProgressResponse(BaseModel):
    id: Optional[int]
    course_id: int

    progress_percent: int
    status: str

    started_at: Optional[datetime]
    last_studied_at: Optional[datetime]
    completed_at: Optional[datetime]

    total_study_minutes: int
    learning_record_count: int

    total_tasks: int
    completed_tasks: int
    task_progress_percent: float


class LearningSummaryResponse(BaseModel):
    course_id: Optional[int]

    total_study_minutes: int
    today_study_minutes: int
    recent_7_days_minutes: int
    learning_record_count: int

    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    overdue_tasks: int

    total_courses: int
    active_courses: int
    completed_courses: int