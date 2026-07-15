import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  Clock3,
  Layers3,
  Sparkles,
} from "lucide-react";
import {
  api,
  type Entity,
  type MultiCoursePlanPreview,
  type MultiCoursePlanRequest,
} from "../../api";
import "./multi-course-planner.css";

interface CourseChoice {
  priority: number;
  deadline: string;
  targetMinutes: number;
}

function localIsoDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function nextRequestId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `multi-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${value}T00:00:00`));
}

export default function MultiCoursePlanner({
  courses,
  notify,
  onCreated,
}: {
  courses: Entity[];
  notify: (message: string) => void;
  onCreated: (plan: Entity) => void;
}) {
  const today = useMemo(() => new Date(), []);
  const initialEnd = useMemo(() => {
    const value = new Date(today);
    value.setDate(value.getDate() + 14);
    return localIsoDate(value);
  }, [today]);
  const [title, setTitle] = useState("期末综合复习");
  const [goal, setGoal] = useState("");
  const [startDate, setStartDate] = useState(localIsoDate(today));
  const [endDate, setEndDate] = useState(initialEnd);
  const [dailyMinutes, setDailyMinutes] = useState(180);
  const [weekdays, setWeekdays] = useState<number[]>([1, 2, 3, 4, 5, 6, 7]);
  const [choices, setChoices] = useState<Record<number, CourseChoice>>({});
  const [preview, setPreview] = useState<MultiCoursePlanPreview | null>(null);
  const [previewRequest, setPreviewRequest] = useState<MultiCoursePlanRequest | null>(null);
  const [requestId, setRequestId] = useState(nextRequestId);
  const [busy, setBusy] = useState<"preview" | "create" | null>(null);
  const [error, setError] = useState("");

  const invalidate = () => {
    setPreview(null);
    setPreviewRequest(null);
    setError("");
  };

  const changeChoice = (courseId: number, patch: Partial<CourseChoice>) => {
    setChoices((current) => ({
      ...current,
      [courseId]: { ...current[courseId], ...patch },
    }));
    invalidate();
  };

  const toggleCourse = (courseId: number) => {
    setChoices((current) => {
      const next = { ...current };
      if (next[courseId]) delete next[courseId];
      else next[courseId] = { priority: 3, deadline: endDate, targetMinutes: 300 };
      return next;
    });
    invalidate();
  };

  const buildRequest = (): MultiCoursePlanRequest => {
    const selected = Object.entries(choices);
    if (selected.length < 2) throw new Error("请至少选择两门课程");
    if (!title.trim()) throw new Error("请填写计划名称");
    if (!weekdays.length) throw new Error("请至少选择一个学习日");
    return {
      title: title.trim(),
      goal: goal.trim() || undefined,
      start_date: startDate,
      end_date: endDate,
      daily_minutes: dailyMinutes,
      available_weekdays: [...weekdays].sort((a, b) => a - b),
      courses: selected.map(([courseId, value]) => ({
        course_id: Number(courseId),
        priority: value.priority,
        deadline: value.deadline,
        target_minutes: value.targetMinutes,
      })),
      client_request_id: requestId,
    };
  };

  const generatePreview = async () => {
    try {
      setError("");
      const request = buildRequest();
      setBusy("preview");
      const result = await api.multiPlanPreview(request);
      setPreview(result);
      setPreviewRequest(request);
    } catch (error) {
      const message = error instanceof Error ? error.message : "预览生成失败";
      setError(message);
      notify(message);
    } finally {
      setBusy(null);
    }
  };

  const confirmCreate = async () => {
    if (!previewRequest) return;
    try {
      setError("");
      setBusy("create");
      const result = await api.createMultiPlan(previewRequest);
      notify(result.created ? "综合规划已创建" : "该规划已确认，无需重复创建");
      setRequestId(nextRequestId());
      onCreated(result.plan);
    } catch (error) {
      const message = error instanceof Error ? error.message : "综合规划创建失败";
      setError(message);
      notify(message);
    } finally {
      setBusy(null);
    }
  };

  const selectedCount = Object.keys(choices).length;
  const weekdayNames = ["一", "二", "三", "四", "五", "六", "日"];

  return (
    <div className="multi-planner">
      <section className="multi-planner-form">
        <div className="multi-section-heading">
          <div>
            <span className="eyebrow">确定性排程</span>
            <h2>把多门课程放进同一张时间表</h2>
            <p>先预览容量与冲突，确认后才会创建真实任务。</p>
          </div>
          <span className="selection-count">已选 {selectedCount} 门</span>
        </div>

        <div className="multi-form-grid">
          <label>
            计划名称
            <input
              value={title}
              maxLength={200}
              onChange={(event) => {
                setTitle(event.target.value);
                invalidate();
              }}
            />
          </label>
          <label>
            每日可用时间
            <div className="input-suffix">
              <input
                type="number"
                min={15}
                max={720}
                value={dailyMinutes}
                onChange={(event) => {
                  setDailyMinutes(Number(event.target.value));
                  invalidate();
                }}
              />
              <span>分钟</span>
            </div>
          </label>
          <label className="span-two">
            综合目标
            <textarea
              value={goal}
              maxLength={5000}
              placeholder="例如：在期末前完成三门课程的重点复习与练习"
              onChange={(event) => {
                setGoal(event.target.value);
                invalidate();
              }}
            />
          </label>
          <label>
            开始日期
            <input
              type="date"
              value={startDate}
              onChange={(event) => {
                setStartDate(event.target.value);
                invalidate();
              }}
            />
          </label>
          <label>
            结束日期
            <input
              type="date"
              value={endDate}
              onChange={(event) => {
                setEndDate(event.target.value);
                invalidate();
              }}
            />
          </label>
        </div>

        <div className="weekday-picker">
          <span>可学习星期</span>
          <div>
            {weekdayNames.map((name, index) => {
              const value = index + 1;
              const active = weekdays.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  className={active ? "active" : ""}
                  onClick={() => {
                    setWeekdays((current) =>
                      active
                        ? current.filter((item) => item !== value)
                        : [...current, value],
                    );
                    invalidate();
                  }}
                >
                  {name}
                </button>
              );
            })}
          </div>
        </div>

        <div className="course-allocation-list">
          <div className="allocation-head">
            <b>课程分配</b>
            <span>为每门课程设置优先级、截止时间与目标学习量</span>
          </div>
          {courses.map((course) => {
            const choice = choices[course.id];
            return (
              <article key={course.id} className={choice ? "selected" : ""}>
                <button
                  type="button"
                  className="course-toggle"
                  aria-label={`${choice ? "取消" : "选择"}${course.name}`}
                  onClick={() => toggleCourse(course.id)}
                >
                  {choice && <Check size={14} />}
                </button>
                <div className="course-identity">
                  <b>{course.name}</b>
                  <span>{course.teacher || "未填写教师"} · {course.semester || "未填写学期"}</span>
                </div>
                {choice && (
                  <div className="course-settings">
                    <label>
                      优先级
                      <select
                        value={choice.priority}
                        onChange={(event) =>
                          changeChoice(course.id, { priority: Number(event.target.value) })
                        }
                      >
                        {[1, 2, 3, 4, 5].map((value) => (
                          <option key={value} value={value}>{value}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      截止日期
                      <input
                        type="date"
                        value={choice.deadline}
                        onChange={(event) =>
                          changeChoice(course.id, { deadline: event.target.value })
                        }
                      />
                    </label>
                    <label>
                      目标分钟
                      <input
                        type="number"
                        min={20}
                        max={100000}
                        value={choice.targetMinutes}
                        onChange={(event) =>
                          changeChoice(course.id, { targetMinutes: Number(event.target.value) })
                        }
                      />
                    </label>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        <button
          type="button"
          className="btn primary multi-preview-button"
          disabled={busy !== null || selectedCount < 2}
          onClick={generatePreview}
        >
          <Sparkles size={16} />
          {busy === "preview" ? "正在计算排程…" : "生成预览"}
        </button>
        {error && <div className="multi-inline-error"><AlertTriangle size={16} /><span>{error}</span></div>}
      </section>

      <section className="multi-preview-panel">
        {!preview ? (
          <div className="multi-preview-empty">
            <Layers3 size={28} />
            <b>先选择课程，再查看综合时间表</b>
            <span>预览不会写入数据库，可以反复调整。</span>
          </div>
        ) : (
          <>
            <div className="capacity-grid">
              <div><Clock3 size={16} /><span>可用容量</span><b>{preview.capacity_minutes}</b><small>分钟</small></div>
              <div><Layers3 size={16} /><span>实际需求</span><b>{preview.required_minutes}</b><small>分钟</small></div>
              <div><Check size={16} /><span>已安排</span><b>{preview.scheduled_minutes}</b><small>分钟</small></div>
              <div className={preview.unscheduled_minutes ? "overload" : ""}><AlertTriangle size={16} /><span>未安排</span><b>{preview.unscheduled_minutes}</b><small>分钟</small></div>
            </div>

            {preview.warnings.length > 0 && (
              <div className="multi-warnings">
                <AlertTriangle size={17} />
                <div>{preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
              </div>
            )}

            <div className="course-summary-bars">
              <h3>课程分配汇总</h3>
              {preview.course_summary.map((item) => {
                const percent = item.required_minutes
                  ? Math.min(100, Math.round(item.scheduled_minutes / item.required_minutes * 100))
                  : 100;
                return (
                  <div key={item.course_id}>
                    <header>
                      <b>{item.course_name}</b>
                      <span>{item.scheduled_minutes} / {item.required_minutes} 分钟</span>
                    </header>
                    <i><span style={{ width: `${percent}%` }} /></i>
                    <small>优先级 {item.priority} · 截止 {item.deadline}</small>
                  </div>
                );
              })}
            </div>

            <div className="daily-schedule">
              <h3><CalendarDays size={17} />按天日程</h3>
              <div className="daily-schedule-scroll">
                {preview.daily_schedule.map((day) => (
                  <article key={day.date}>
                    <header><b>{formatDate(day.date)}</b><span>{day.total_minutes} 分钟</span></header>
                    {day.tasks.map((task) => (
                      <div key={`${day.date}-${task.course_id}`}>
                        <span>{task.course_name}</span>
                        <b>{task.estimated_minutes} 分钟</b>
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            </div>

            <div className="multi-confirm-bar">
              <div>
                <b>预览满意后再确认</b>
                <span>确认会一次性创建计划、课程关联和日程任务。</span>
              </div>
              <button
                type="button"
                className="btn primary"
                disabled={busy !== null}
                onClick={confirmCreate}
              >
                {busy === "create" ? "正在创建…" : "确认创建"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
