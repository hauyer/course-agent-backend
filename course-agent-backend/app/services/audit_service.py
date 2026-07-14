from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.audit_log import AuditLog


def write_audit_log(**values: Any) -> None:
    """使用独立事务写审计记录，避免影响主业务事务。"""
    db = SessionLocal()
    try:
        db.add(AuditLog(**values))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def list_audit_logs(
    db: Session,
    *,
    user_id: int,
    limit: int = 100,
    category: str | None = None,
) -> list[AuditLog]:
    query = db.query(AuditLog).filter(AuditLog.user_id == user_id)
    if category:
        query = query.filter(AuditLog.category == category)
    return query.order_by(AuditLog.id.desc()).limit(limit).all()
