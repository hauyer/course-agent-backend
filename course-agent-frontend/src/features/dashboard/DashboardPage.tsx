import { useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis } from "recharts";
import { Check, ChevronRight, Clock3, FileText, Library, RefreshCw, Target } from "lucide-react";

import { api, type Entity } from "../../api";

const labels: Record<string, string> = { pending: "待开始", in_progress: "进行中", completed: "已完成", cancelled: "已取消" };
function dayText(value?: string) { return value ? new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)) : "—"; }
function Loading({ error }: { error?: string }) { return <div className="empty"><RefreshCw className="spin" size={20}/><b>{error || "正在整理数据"}</b><span>{error ? "检查后端服务后刷新页面" : "请稍候"}</span></div>; }
function Empty({ title, text }: { title: string; text: string }) { return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>; }
function Status({ value }: { value: string }) { return <span className={`status ${value}`}>{labels[value] || value}</span>; }
function PanelHead({ title, action, onClick }: { title: string; action?: string; onClick?: () => void }) { return <div className="panel-head"><h2>{title}</h2>{action && <button className="text-btn" onClick={onClick}>{action}<ChevronRight size={14}/></button>}</div>; }

export default function DashboardPage({ go }: { go: (page: any) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => { let live = true; api.dashboard(14).then((value) => live && setData(value)).catch((reason) => live && setError(reason instanceof Error ? reason.message : "加载失败")); return () => { live = false; }; }, []);
  if (!data) return <Loading error={error} />;
  const summary = data.summary || {};
  const stats = [
    ["今日学习", `${summary.today_study_minutes || 0} 分钟`, Clock3],
    ["待完成任务", summary.pending_tasks || 0, Check],
    ["进行中计划", summary.active_plans || 0, Target],
    ["课程资料", summary.total_materials || 0, FileText],
  ] as any[];
  return <div className="stack">
    <div className="date-line"><span>{new Intl.DateTimeFormat("zh-CN", { weekday: "long", month: "long", day: "numeric" }).format(new Date())}</span><i/></div>
    <div className="stat-grid">{stats.map(([label, value, Icon]) => <div className="stat" key={label}><Icon size={18}/><span>{label}</span><strong>{value}</strong></div>)}</div>
    <div className="dashboard-grid">
      <div className="panel span2"><PanelHead title="近 14 天投入" action="学习记录" onClick={() => go("records")}/><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.study_trend}><defs><linearGradient id="study" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#68785f" stopOpacity=".35"/><stop offset="1" stopColor="#68785f" stopOpacity="0"/></linearGradient></defs><XAxis dataKey="date" axisLine={false} tickLine={false} tickFormatter={(value: string) => value.slice(5)} fontSize={11}/><ChartTooltip formatter={(value: any) => [`${value} 分钟`, "学习"]}/><Area type="monotone" dataKey="minutes" stroke="#68785f" strokeWidth={2} fill="url(#study)"/></AreaChart></ResponsiveContainer></div></div>
      <div className="panel"><PanelHead title="今日任务" action="全部任务" onClick={() => go("tasks")}/>{data.today_task_items?.length ? <div className="compact-list">{data.today_task_items.map((task: Entity) => <div key={task.id}><span className={`priority-dot ${task.priority}`}/><div><b>{task.title}</b><small>{task.course_name || "通用任务"} · {task.estimated_minutes || "—"} 分钟</small></div><Status value={task.status}/></div>)}</div> : <Empty title="今天没有待办" text="可以从学习计划中安排下一步"/>}</div>
      <div className="panel"><PanelHead title="活跃计划" action="管理计划" onClick={() => go("plans")}/>{data.active_plan_items?.length ? <div className="plan-list">{data.active_plan_items.map((plan: Entity) => <div key={plan.id}><div><b>{plan.title}</b><span>{plan.completed_tasks}/{plan.total_tasks}</span></div><div className="progress"><i style={{ width: `${plan.progress_percent}%` }}/></div><small>{plan.progress_percent}% · 截止 {dayText(plan.end_date)}</small></div>)}</div> : <Empty title="暂无进行中的计划" text="建立一份计划，让目标落到日期上"/>}</div>
      <div className="panel span2"><PanelHead title="课程进展" action="课程管理" onClick={() => go("courses")}/><div className="course-strip">{data.course_items?.map((course: Entity) => <div key={course.id}><span>{course.semester || "本学期"}</span><b>{course.name}</b><small>{course.teacher || "未填写教师"}</small><div className="progress"><i style={{ width: `${course.course_progress_percent}%` }}/></div><em>{course.course_progress_percent}% · {course.total_study_minutes} 分钟</em></div>)}</div></div>
    </div>
  </div>;
}
