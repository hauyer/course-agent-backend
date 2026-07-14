from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class LearningRecord(Base):
    """用户的一次真实学习记录。"""

    __tablename__ = "learning_records"

    __table_args__ = (
        Index(
            "ix_learning_records_user_course_time",
            "user_id",
            "course_id",
            "studied_at",
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

    # 可以记录“学习了哪一份资料”
    material_id = Column(
        Integer,
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 可以记录“完成了哪一个任务”
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    studied_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    duration_minutes = Column(
        Integer,
        nullable=False,
    )

    # manual、material、task、study_plan
    source = Column(
        String(30),
        nullable=False,
        default="manual",
    )

    content_summary = Column(
        Text,
        nullable=True,
    )

    reflection = Column(
        Text,
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