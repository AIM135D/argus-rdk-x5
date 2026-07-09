import { AlertTriangle, CheckCircle2, Circle, XCircle } from "lucide-react";

type StatusLevel = "ok" | "warn" | "error" | "idle" | "running";

interface Props {
  title: string;
  detail?: string;
  level?: StatusLevel;
}

export default function StatusCard({ title, detail, level = "idle" }: Props) {
  const Icon = level === "ok" ? CheckCircle2 : level === "warn" ? AlertTriangle : level === "error" ? XCircle : Circle;
  return (
    <div className={`status-card ${level}`}>
      <Icon size={20} />
      <div>
        <div className="status-title">{title}</div>
        {detail ? <div className="status-detail">{detail}</div> : null}
      </div>
    </div>
  );
}
