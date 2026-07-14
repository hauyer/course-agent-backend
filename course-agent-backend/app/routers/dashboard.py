from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import (
    DashboardOverviewResponse,
)
from app.services.auth_service import (
    get_current_user,
)
from app.services.dashboard_service import (
    get_dashboard_overview,
)


router = APIRouter()


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="获取首页综合统计看板",
)
def get_dashboard_overview_api(
    trend_days: int = Query(
        default=7,
        ge=7,
        le=30,
        description="学习趋势统计天数",
    ),
    task_limit: int = Query(
        default=8,
        ge=1,
        le=30,
        description="今日和后续任务返回数量",
    ),
    plan_limit: int = Query(
        default=5,
        ge=1,
        le=20,
        description="活跃学习计划返回数量",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    return get_dashboard_overview(
        db=db,
        user_id=current_user.id,
        trend_days=trend_days,
        task_limit=task_limit,
        plan_limit=plan_limit,
    )