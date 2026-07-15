from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class StudyPlanCourse(Base):
    """A verified course allocation inside a multi-course study plan."""

    __tablename__ = "study_plan_courses"
    __table_args__ = (
        UniqueConstraint(
            "study_plan_id",
            "course_id",
            name="uq_study_plan_courses_plan_course",
        ),
        Index(
            "ix_study_plan_courses_user_plan",
            "user_id",
            "study_plan_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    study_plan_id = Column(
        Integer,
        ForeignKey("study_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority = Column(Integer, nullable=False)
    deadline = Column(Date, nullable=False, index=True)
    target_minutes = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
