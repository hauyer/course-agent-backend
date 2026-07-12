from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv

load_dotenv()


def _get_user_id(config: RunnableConfig) -> int:
    try:
        return int(config.get("configurable", {}).get("user_id", 1))
    except (ValueError, TypeError):
        return 1


def _get_db():
    from app.database import SessionLocal
    return SessionLocal()


@tool
def search_courses(keyword: str, config: RunnableConfig) -> str:
    """根据关键词搜索课程库，返回匹配的课程信息。关键词如 python、数学、英语、机器学习。"""
    from app.services.course_service import get_user_courses
    db = _get_db()
    try:
        courses = get_user_courses(db, user_id=_get_user_id(config))
        keyword_lower = keyword.lower()
        matched = [
            c for c in courses
            if keyword_lower in (c.name or "").lower()
            or keyword_lower in (c.description or "").lower()
            or keyword_lower in (c.teacher or "").lower()
        ]
        if not matched:
            return f"未找到'{keyword}'相关课程"
        lines = []
        for c in matched:
            teacher = f", {c.teacher}老师" if c.teacher else ""
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"{c.name}{teacher}{desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"课程查询失败：{e}"
    finally:
        db.close()


@tool
def list_all_courses(config: RunnableConfig) -> str:
    """列出全部课程"""
    from app.services.course_service import get_user_courses
    db = _get_db()
    try:
        courses = get_user_courses(db, user_id=_get_user_id(config))
        if not courses:
            return "暂无课程"
        lines = []
        for c in courses:
            teacher = f", {c.teacher}老师" if c.teacher else ""
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"{c.name}{teacher}{desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"课程列表获取失败：{e}"
    finally:
        db.close()


@tool
def create_course(name: str, teacher: str = "", hours: int = 0, config: RunnableConfig = None) -> str:
    """创建新的课程到管理端。name 课程名，teacher 授课教师，hours 课时数"""
    from app.services.course_service import create_course as svc_create_course
    from app.schemas.course import CourseCreate
    db = _get_db()
    try:
        course_in = CourseCreate(
            name=name,
            teacher=teacher or None,
            description=f"{hours}课时" if hours else None,
        )
        course = svc_create_course(db, user_id=_get_user_id(config), course_in=course_in)
        return f"课程'{course.name}'创建成功（ID: {course.id}）"
    except Exception as e:
        return f"课程创建失败：{e}"
    finally:
        db.close()
