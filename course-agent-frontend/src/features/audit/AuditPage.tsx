import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, Clock3, RefreshCw, TriangleAlert, Wrench } from "lucide-react";

import { api, type Entity } from "../../api";
import "./audit.css";

export default function AuditPage() {
  const [overview, setOverview] = useState<Entity | null>(null);
  const [logs, setLogs] = useState<Entity[]>([]);
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      const [summary, rows]: any[] = await Promise.all([
        api.auditOverview(),
        api.auditLogs(category),
      ]);
      setOverview(summary);
      setLogs(Array.isArray(rows) ? rows : []);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, [category]);

  const maxDuration = useMemo(
    () => Math.max(1, ...logs.slice(0, 24).map((item) => Number(item.duration_ms || 0))),
    [logs],
  );

  const cards = [
    [Activity, "请求", overview?.request_count || 0],
    [Clock3, "平均耗时", `${overview?.avg_duration_ms || 0} ms`],
    [Bot, "模型调用", overview?.model_calls || 0],
    [Wrench, "工具调用", overview?.tool_calls || 0],
    [TriangleAlert, "工具错误率", `${overview?.tool_error_rate || 0}%`],
    [TriangleAlert, "异常", overview?.error_count || 0],
  ];

  return (
    <div className="audit-page stack">
      <div className="audit-toolbar">
        <div>
          <h2>运行健康概览</h2>
          <p>只记录性能、状态与匿名摘要，不保存密码、密钥或完整对话正文。</p>
        </div>
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">全部类型</option>
          <option value="agent">Agent</option>
          <option value="http">HTTP</option>
          <option value="error">异常</option>
        </select>
        <button className="btn subtle" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={14} className={loading ? "spin" : ""} /> 刷新
        </button>
      </div>
      <div className="audit-stats">
        {cards.map(([Icon, label, value]: any[]) => (
          <article key={label}>
            <Icon size={17} />
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <section className="audit-panel">
        <header><h2>近期请求耗时</h2><span>最近 24 条</span></header>
        <div className="audit-bars">
          {logs.slice(0, 24).reverse().map((item) => (
            <i
              key={item.id}
              className={item.error_count ? "error" : item.category}
              style={{ height: `${Math.max(5, Number(item.duration_ms || 0) / maxDuration * 100)}%` }}
              title={`${item.summary || item.path} · ${item.duration_ms} ms`}
            />
          ))}
        </div>
      </section>
      <section className="audit-panel audit-table-wrap">
        <header><h2>审核日志</h2><span>{logs.length} 条</span></header>
        <table className="audit-table">
          <thead><tr><th>状态</th><th>类型</th><th>摘要</th><th>耗时</th><th>模型 / 工具</th><th>Token</th><th>追踪号</th><th>时间</th></tr></thead>
          <tbody>
            {logs.map((item) => (
              <tr key={item.id}>
                <td><span className={`audit-code ${item.status_code >= 400 ? "bad" : ""}`}>{item.status_code}</span></td>
                <td>{item.category}</td>
                <td title={item.error_detail || ""}>{item.summary || item.path}</td>
                <td>{item.duration_ms} ms</td>
                <td>{item.model_calls} / {item.tool_calls}</td>
                <td>{Number(item.prompt_tokens || 0) + Number(item.completion_tokens || 0)}</td>
                <td><code>{String(item.trace_id || "").slice(0, 12)}</code></td>
                <td>{new Date(item.created_at).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !logs.length && <div className="audit-empty">还没有可展示的运行日志</div>}
      </section>
    </div>
  );
}
