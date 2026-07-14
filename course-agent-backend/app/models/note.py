from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base


class Note(Base):
    """课程学习助手中的课程笔记。"""

    __tablename__ = "notes"

    __table_args__ = (
        Index(
            "ix_notes_user_course_updated",
            "user_id",
            "course_id",
            "updated_at",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
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

    title = Column(
        String(200),
        nullable=False,
    )

    # 使用 Markdown 作为系统内统一笔记格式
    content_markdown = Column(
        LONGTEXT,
        nullable=False,
    )

    # MySQL JSON，例如 ["操作系统", "进程", "重点"]
    tags = Column(
        JSON,
        nullable=False,
        default=list,
    )

    # manual、summary、knowledge_point、review
    note_type = Column(
        String(30),
        nullable=False,
        default="manual",
        index=True,
    )

    # manual、material、agent
    source = Column(
        String(30),
        nullable=False,
        default="manual",
        index=True,
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