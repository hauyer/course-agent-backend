from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable


MIN_BLOCK_MINUTES = 20
STANDARD_BLOCK_MINUTES = 25


@dataclass(frozen=True)
class PlannerCourse:
    course_id: int
    course_name: str
    priority: int
    deadline: date
    target_minutes: int
    progress_percent: int = 0
    existing_task_minutes: int = 0

    @property
    def required_minutes(self) -> int:
        completed = round(
            self.target_minutes * max(0, min(self.progress_percent, 100)) / 100
        )
        return max(
            self.target_minutes - completed - max(self.existing_task_minutes, 0),
            0,
        )


def _date_range(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _task_priority(value: int) -> str:
    if value >= 5:
        return "urgent"
    if value == 4:
        return "high"
    if value == 3:
        return "medium"
    return "low"


def build_multi_course_schedule(
    *,
    start_date: date,
    end_date: date,
    daily_minutes: int,
    available_weekdays: list[int],
    courses: list[PlannerCourse],
) -> dict[str, Any]:
    """Build a deterministic schedule without calling an LLM or writing data."""

    if end_date < start_date:
        raise ValueError("计划结束日期不能早于开始日期")
    if not 15 <= daily_minutes <= 720:
        raise ValueError("每日可用时间必须位于 15 到 720 分钟")
    weekdays = sorted(set(available_weekdays))
    if not weekdays or any(day < 1 or day > 7 for day in weekdays):
        raise ValueError("可学习星期必须位于 1 到 7")
    if len(courses) < 2:
        raise ValueError("综合规划至少需要两门课程")

    available_dates = [
        item for item in _date_range(start_date, end_date) if item.isoweekday() in weekdays
    ]
    initial = {item.course_id: item.required_minutes for item in courses}
    remaining = dict(initial)
    scheduled = {item.course_id: 0 for item in courses}
    total_required = sum(initial.values())
    weights = {
        item.course_id: round(
            item.priority * (1.0 + (initial[item.course_id] / total_required if total_required else 0)),
            4,
        )
        for item in courses
    }
    by_id = {item.course_id: item for item in courses}
    daily_schedule: list[dict[str, Any]] = []

    for planned_date in available_dates:
        capacity = daily_minutes
        allocations: dict[int, int] = {}
        allocation_order: list[int] = []

        while capacity > 0:
            candidates = [
                item
                for item in courses
                if remaining[item.course_id] > 0 and planned_date <= item.deadline
            ]
            if not candidates:
                break

            def score(item: PlannerCourse):
                required = max(initial[item.course_id], 1)
                days_left = max((item.deadline - planned_date).days, 0)
                remaining_ratio = remaining[item.course_id] / required
                fairness = 1.0 - scheduled[item.course_id] / required
                pressure = item.priority * 3.0 + remaining_ratio * 2.0 + fairness
                urgency = 6.0 / (days_left + 1)
                return (
                    -(pressure + urgency),
                    item.deadline,
                    -remaining[item.course_id],
                    item.course_id,
                )

            selected = sorted(candidates, key=score)[0]
            course_id = selected.course_id
            block = min(STANDARD_BLOCK_MINUTES, capacity, remaining[course_id])
            if block < MIN_BLOCK_MINUTES:
                if course_id not in allocations and remaining[course_id] > capacity:
                    break
            if course_id not in allocations:
                allocation_order.append(course_id)
                allocations[course_id] = 0
            allocations[course_id] += block
            scheduled[course_id] += block
            remaining[course_id] -= block
            capacity -= block

        tasks: list[dict[str, Any]] = []
        for course_id in allocation_order:
            item = by_id[course_id]
            minutes = allocations[course_id]
            tasks.append(
                {
                    "course_id": course_id,
                    "course_name": item.course_name,
                    "title": f"学习{item.course_name} · {planned_date:%m/%d}",
                    "description": (
                        "由综合规划根据课程截止时间、优先级和剩余学习量确定。"
                    ),
                    "priority": _task_priority(item.priority),
                    "estimated_minutes": minutes,
                    "planned_date": planned_date,
                    "due_at": datetime.combine(planned_date, time(23, 59, 59)),
                }
            )
        if tasks:
            daily_schedule.append(
                {
                    "date": planned_date,
                    "total_minutes": sum(item["estimated_minutes"] for item in tasks),
                    "tasks": tasks,
                    "course_summary": [
                        {
                            "course_id": item["course_id"],
                            "course_name": item["course_name"],
                            "minutes": item["estimated_minutes"],
                        }
                        for item in tasks
                    ],
                    "warnings": [],
                }
            )

    course_summary: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in sorted(courses, key=lambda value: value.course_id):
        unscheduled = remaining[item.course_id]
        course_summary.append(
            {
                "course_id": item.course_id,
                "course_name": item.course_name,
                "priority": item.priority,
                "deadline": item.deadline,
                "target_minutes": item.target_minutes,
                "progress_percent": max(0, min(item.progress_percent, 100)),
                "existing_task_minutes": max(item.existing_task_minutes, 0),
                "required_minutes": initial[item.course_id],
                "scheduled_minutes": scheduled[item.course_id],
                "unscheduled_minutes": unscheduled,
                "weight": weights[item.course_id],
            }
        )
        if unscheduled:
            warnings.append(
                f"{item.course_name} 仍有 {unscheduled} 分钟无法在截止日期前安排"
            )

    scheduled_minutes = sum(scheduled.values())
    unscheduled_minutes = sum(remaining.values())
    capacity_minutes = len(available_dates) * daily_minutes
    if not available_dates:
        warnings.insert(0, "当前日期范围内没有可学习日期")
    if unscheduled_minutes:
        warnings.append(
            f"总容量不足或截止日期过近，缺少 {unscheduled_minutes} 分钟；"
            "请增加每日时间、开放更多星期或延长截止日期"
        )

    return {
        "capacity_minutes": capacity_minutes,
        "required_minutes": total_required,
        "scheduled_minutes": scheduled_minutes,
        "unscheduled_minutes": unscheduled_minutes,
        "warnings": warnings,
        "daily_schedule": daily_schedule,
        "course_summary": course_summary,
    }
