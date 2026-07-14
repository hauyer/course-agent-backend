from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class NoteSyncRecord(Base):
    """记录笔记与外部笔记平台之间的同步关系。"""

    __tablename__ = "note_sync_records"

    __table_args__ = (
        UniqueConstraint(
            "note_id",
            "provider",
            name="uq_note_sync_provider",
        ),
        Index(
            "ix_note_sync_records_note_provider",
            "note_id",
            "provider",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    note_id = Column(
        Integer,
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # obsidian、notion
    provider = Column(
        String(30),
        nullable=False,
        index=True,
    )

    # Notion 后续使用 page_id
    external_id = Column(
        String(255),
        nullable=True,
    )

    # Obsidian 使用 Vault 内部相对路径
    external_path = Column(
        String(1000),
        nullable=True,
    )

    # success、failed、pending
    sync_status = Column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    # 用于判断内容有没有变化
    content_hash = Column(
        String(64),
        nullable=True,
    )

    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error = Column(
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