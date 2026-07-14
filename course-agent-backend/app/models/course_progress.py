from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class CourseProgress(Base):
    """用户在一门课程中的总体学习进度。"""

    __tablename__ = "course_progresses"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "course_id",
            name="uq_course_progress_user_course",
        ),
        Index(
            "ix_course_progress_user_status",
            "user_id",
            "status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
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

    # 0—100
    progress_percent = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # not_started、in_progress、paused、completed
    status = Column(
        String(30),
        nullable=False,
        default="not_started",
        index=True,
    )

    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_studied_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )