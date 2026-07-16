import { Clipboard, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getJob, getTaskStatus, runConvert } from "../api";
import { TFunc } from "../i18n";
import LogPanel from "../components/LogPanel";
import ProgressSteps from "../components/ProgressSteps";
import StatusCard from "../components/StatusCard";

interface Props {
  t: TFunc;
  modelInput: Record<string, any>;
  onResult: (value: Record<string, any>) => void;
}

const DEFAULT_STEPS = [
  "[1/8] 准备任务目录",
  "[2/8] 校准集质量检查",
  "[3/8] 导出 ONNX",
  "[4/8] 检查 ONNX 结构",
  "[5/8] hb_mapper checker",
  "[6/8] INT8 量化编译 makertbin",
  "[7/8] 生成 deploy_config.py",
  "[8/8] 生成 deploy_report.md"
].map((name) => ({ name, status: "waiting", message: "" }));

function collectDiagnosis(result: any): any[] {
  if (!result || typeof result !== "object") return [];
  const list: any[] = [];
  const walk = (value: any) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (Array.isArray(value.diagnosis)) list.push(...value.diagnosis);
    Object.values(value).forEach(walk);
  };
  walk(result);
  return list;
}

export default function ConvertPage({ t, modelInput, onResult }: Props) {
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState("");

  const canRun = Boolean(modelInput.pt_path && (modelInput.data_yaml_path || (modelInput.calibration_dir && modelInput.manual_classes?.length)));
  const appLog = job?.result?.app_log || (status?.task_dir ? `${status.task_dir}\\logs\\app.log` : "");
  const diagnoses = useMemo(() => collectDiagnosis(job?.result), [job]);

  const start = async () => {
    setError("");
    if (!canRun) {
      setError(t("convert.needInput"));
      return;
    }
    const payload = {
      ...modelInput,
      manual_classes: modelInput.manual_classes ?? ["person", "helmet", "reflective_vest"]
    };
    const result = await runConvert(payload);
    setJobId(result.job_id);
    setJob(result);
  };

  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(async () => {
      const next = await getJob(jobId);
      setJob(next);
      const statusPath = next.result?.status_path;
      if (statusPath) {
        try {
          setStatus(await getTaskStatus(statusPath));
        } catch {
          // The status file may not exist during the first milliseconds of the job.
        }
      }
      if (next.status === "success" || next.status === "failed") {
        window.clearInterval(timer);
        if (next.result) onResult(next.result);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [jobId]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{t("convert.title")}</h1>
          <p>{t("convert.subtitle")}</p>
        </div>
        <button className="primary-action" onClick={start} disabled={!canRun || job?.status === "running"}>
          <Play size={17} />
          {job?.status === "running" ? t("convert.running") : t("convert.start")}
        </button>
      </div>

      {error ? <div className="inline-error">{error}</div> : null}
      <div className="summary-strip">
        <StatusCard title={t("convert.job")} detail={job?.status ?? "idle"} level={job?.status === "success" ? "ok" : job?.status === "failed" ? "error" : job?.status ? "warn" : "idle"} />
        <StatusCard title={t("convert.taskDir")} detail={job?.result?.task_dir ?? status?.task_dir ?? "waiting"} level="idle" />
      </div>

      <ProgressSteps steps={status?.steps ?? DEFAULT_STEPS} />

      {diagnoses.length ? (
        <section className="section-block">
          <div className="panel-title-row">
            <h2>{t("convert.diagnosis")}</h2>
            <button className="secondary-action slim" onClick={() => navigator.clipboard.writeText(JSON.stringify(diagnoses, null, 2))}>
              <Clipboard size={15} />
              {t("convert.copy")}
            </button>
          </div>
          <div className="diagnosis-list">
            {diagnoses.map((item, index) => (
              <div className="notice" key={`${item.code}-${index}`}>
                <strong>{item.code}</strong>
                <span>{item.reason}</span>
                <span>{item.suggestion}</span>
                <code>{item.command}</code>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <LogPanel title="app.log" logPath={appLog} />
      {job?.result?.logs?.export ? <LogPanel title="export_onnx.log" logPath={job.result.logs.export} /> : null}
      {job?.result?.logs?.mapper ? <LogPanel title="mapper_logs.txt" logPath={job.result.logs.mapper} /> : null}
    </div>
  );
}
