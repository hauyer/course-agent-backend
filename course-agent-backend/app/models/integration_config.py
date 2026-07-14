from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class IntegrationConfig(Base):
    """External note integrations owned by exactly one application user."""

    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_integration_config_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Secrets are encrypted at rest with a key derived from SECRET_KEY.
    notion_api_key_encrypted = Column(Text, nullable=True)
    notion_parent_page_id = Column(String(255), nullable=True)
    notion_api_version = Column(String(30), nullable=False, default="2026-03-11")
    notion_timeout_seconds = Column(Integer, nullable=False, default=30)

    obsidian_vault_path = Column(String(2000), nullable=True)
    obsidian_base_folder = Column(String(255), nullable=False, default="课程学习助手")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
