import { Clipboard, Maximize2, Minimize2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { readLog } from "../api";

interface Props {
  title: string;
  logPath?: string;
  content?: string;
  refreshMs?: number;
}

export default function LogPanel({ title, logPath, content, refreshMs = 2000 }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [log, setLog] = useState(content ?? "");
  const [error, setError] = useState("");

  const load = async () => {
    if (!logPath) {
      setLog(content ?? "");
      return;
    }
    try {
      const result = await readLog(logPath);
      setLog(result.content ?? "");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    load();
    if (!logPath) return;
    const timer = window.setInterval(load, refreshMs);
    return () => window.clearInterval(timer);
  }, [logPath, content, refreshMs]);

  return (
    <section className={`log-panel ${expanded ? "expanded" : ""}`}>
      <div className="panel-title-row">
        <h3>{title}</h3>
        <div className="icon-actions">
          <button title="Refresh log / 刷新日志" onClick={load}>
            <RefreshCw size={16} />
          </button>
          <button title="Copy log / 复制日志" onClick={() => navigator.clipboard.writeText(log)}>
            <Clipboard size={16} />
          </button>
          <button title={expanded ? "Collapse log / 收起日志" : "Expand log / 展开日志"} onClick={() => setExpanded(!expanded)}>
            {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>
      {logPath ? <div className="muted path-line">{logPath}</div> : null}
      {error ? <div className="inline-error">{error}</div> : null}
      <pre>{log || "No log yet / 暂无日志"}</pre>
    </section>
  );
}
