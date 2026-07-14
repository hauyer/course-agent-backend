from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_service import list_audit_logs
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/logs")
def audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = list_audit_logs(
        db,
        user_id=current_user.id,
        limit=limit,
        category=category,
    )
    return [
        {
            "id": row.id,
            "trace_id": row.trace_id,
            "category": row.category,
            "method": row.method,
            "path": row.path,
            "status_code": row.status_code,
            "duration_ms": round(row.duration_ms or 0, 1),
            "model_calls": row.model_calls,
            "tool_calls": row.tool_calls,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "error_count": row.error_count,
            "summary": row.summary,
            "error_detail": row.error_detail,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/overview")
def audit_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    values = (
        db.query(
            func.count(AuditLog.id),
            func.coalesce(func.avg(AuditLog.duration_ms), 0),
            func.coalesce(func.sum(AuditLog.model_calls), 0),
            func.coalesce(func.sum(AuditLog.tool_calls), 0),
            func.coalesce(func.sum(AuditLog.prompt_tokens + AuditLog.completion_tokens), 0),
            func.coalesce(func.sum(AuditLog.error_count), 0),
        )
        .filter(AuditLog.user_id == current_user.id)
        .one()
    )
    agent_values = (
        db.query(
            func.coalesce(func.sum(AuditLog.tool_calls), 0),
            func.coalesce(func.sum(AuditLog.error_count), 0),
        )
        .filter(
            AuditLog.user_id == current_user.id,
            AuditLog.category == "agent",
        )
        .one()
    )
    tool_calls = int(agent_values[0])
    tool_errors = int(agent_values[1])
    return {
        "request_count": int(values[0]),
        "avg_duration_ms": round(float(values[1]), 1),
        "model_calls": int(values[2]),
        "tool_calls": int(values[3]),
        "total_tokens": int(values[4]),
        "error_count": int(values[5]),
        "tool_error_rate": round(min(tool_errors / tool_calls * 100, 100), 1) if tool_calls else 0,
    }
