import { Play, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { checkEnv, getJob, installEnv } from "../api";
import { TFunc } from "../i18n";
import LogPanel from "../components/LogPanel";
import StatusCard from "../components/StatusCard";

interface Props {
  t: TFunc;
  env?: any;
  onEnv: (env: any) => void;
}

function Section({ title, data }: { title: string; data: Record<string, any> }) {
  if (!data) return null;
  return (
    <section className="section-block">
      <h2>{title}</h2>
      <div className="status-grid compact">
        {Object.entries(data).map(([key, item]) => (
          <StatusCard key={key} title={item.name ?? key} detail={String(item.detail ?? "")} level={item.level ?? (item.ok ? "ok" : "error")} />
        ))}
      </div>
    </section>
  );
}

export default function EnvCheckPage({ t, env, onEnv }: Props) {
  const [localEnv, setLocalEnv] = useState<any>(env);
  const [checking, setChecking] = useState(false);
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<any>(null);
  const [error, setError] = useState("");

  const runCheck = async () => {
    setChecking(true);
    setError("");
    try {
      const result = await checkEnv();
      setLocalEnv(result);
      onEnv(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };

  const runInstall = async () => {
    setError("");
    const result = await installEnv();
    setJobId(result.job_id);
    setJob(result);
  };

  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(async () => {
      const next = await getJob(jobId);
      setJob(next);
      if (next.status === "success" || next.status === "failed") {
        window.clearInterval(timer);
        if (next.result?.after) {
          setLocalEnv(next.result.after);
          onEnv(next.result.after);
        }
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [jobId, onEnv]);

  return (
    <div className="page">
      <div className="page-header hero-header">
        <div>
          <h1>{t("env.title")}</h1>
          <p>{t("env.subtitle")}</p>
        </div>
        <div className="actions">
          <button className="secondary-action" onClick={runCheck} disabled={checking}>
            <Play size={17} />
            {checking ? t("env.checking") : t("env.check")}
          </button>
          <button className="primary-action" onClick={runInstall}>
            <Wrench size={17} />
            {t("env.prepare")}
          </button>
        </div>
      </div>

      {error ? <div className="inline-error">{error}</div> : null}
      {localEnv?.summary ? (
        <div className="summary-strip">
          <StatusCard title={t("env.summary")} detail={`${localEnv.summary.errors.length} errors / ${localEnv.summary.warnings.length} warnings`} level={localEnv.summary.ok ? "ok" : "warn"} />
          <StatusCard title={t("env.report")} detail={localEnv.report_path} level="idle" />
        </div>
      ) : null}

      {job ? (
        <section className="section-block">
          <h2>{t("env.installJob")}</h2>
          <StatusCard title={t("env.jobStatus")} detail={job.status} level={job.status === "success" ? "ok" : job.status === "failed" ? "error" : "warn"} />
          {job.result?.user_actions?.length ? (
            <div className="notice-list">
              {job.result.user_actions.map((item: any) => (
                <div className="notice" key={item.title}>
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                </div>
              ))}
            </div>
          ) : null}
          {job.result?.log_path ? <LogPanel title="install.log" logPath={job.result.log_path} /> : null}
        </section>
      ) : null}

      <Section title={t("env.windows")} data={localEnv?.windows} />
      <Section title={t("env.wsl")} data={localEnv?.wsl} />
      <Section title={t("env.docker")} data={localEnv?.docker} />
      <Section title={t("env.conda")} data={localEnv?.conda} />
      <Section title={t("env.pythonPackages")} data={localEnv?.python_packages} />
      <Section title={t("env.rdk")} data={localEnv?.rdk_model_zoo} />
    </div>
  );
}
