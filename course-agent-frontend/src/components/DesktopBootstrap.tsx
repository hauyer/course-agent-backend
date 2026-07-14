import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Database, RefreshCw, ShieldCheck } from "lucide-react";

import "./desktop-bootstrap.css";

type Status = {
  configured?: boolean;
  backend_ready?: boolean;
  development?: boolean;
  host?: string;
  port?: number;
  username?: string;
  database?: string;
};

export default function DesktopBootstrap({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const inspect = async () => {
    try {
      const response = await fetch("/desktop/config", { cache: "no-store" });
      if (response.status === 404) {
        setStatus({ configured: true, backend_ready: true, development: true });
        return;
      }
      setStatus(await response.json());
    } catch {
      setStatus({ configured: true, backend_ready: true, development: true });
    }
  };

  useEffect(() => {
    void inspect();
  }, []);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = Object.fromEntries(new FormData(event.currentTarget));
      const response = await fetch("/desktop/config", {
        method: status?.configured ? "PUT" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "配置保存失败");
      setStatus(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "配置保存失败");
    } finally {
      setBusy(false);
    }
  };

  if (status?.configured && status.backend_ready) return <>{children}</>;

  return (
    <main className="desktop-bootstrap">
      <section className="bootstrap-intro">
        <div className="bootstrap-brand"><span>课</span><b>学习工作台</b></div>
        <div>
          <small>首次运行配置</small>
          <h1>连接你的本地 MySQL</h1>
          <p>数据库密码由 Windows 系统凭据加密，仅在启动本机 FastAPI 时临时解密，不会写入安装包或上传到 GitHub。</p>
        </div>
        <ul>
          <li><ShieldCheck size={17} />安装包不携带真实 .env</li>
          <li><Database size={17} />继续使用可扩展的 MySQL</li>
        </ul>
      </section>
      <section className="bootstrap-form-panel">
        <form onSubmit={save}>
          <header>
            <span>数据库连接</span>
            <h2>{status?.configured ? "修正 MySQL 配置" : "完成首次配置"}</h2>
            <p>请先按 README 创建数据库，再填写有权限访问该数据库的账号。</p>
          </header>
          <div className="bootstrap-grid">
            <label className="wide">主机地址<input name="host" defaultValue={status?.host || "127.0.0.1"} required /></label>
            <label>端口<input name="port" type="number" min="1" max="65535" defaultValue={status?.port || 3306} required /></label>
            <label>数据库名<input name="database" defaultValue={status?.database || "course_agent"} required /></label>
            <label>用户名<input name="username" defaultValue={status?.username || "course_agent"} required /></label>
            <label>密码<input name="password" type="password" autoComplete="off" required /></label>
          </div>
          {status?.configured && !status.backend_ready && !error && (
            <div className="bootstrap-error">已有配置当前无法连接，请重新输入密码并检查 MySQL 服务。</div>
          )}
          {error && <div className="bootstrap-error">{error}</div>}
          <button disabled={busy}>
            {busy ? <><RefreshCw className="spin" size={16} />正在验证并启动后端…</> : "保存并进入工作台"}
          </button>
          <footer>配置保存在当前 Windows 用户的 AppData 目录，不同系统账户互不共享。</footer>
        </form>
      </section>
    </main>
  );
}
