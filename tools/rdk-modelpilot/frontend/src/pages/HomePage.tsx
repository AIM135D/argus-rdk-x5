import { ArrowRight } from "lucide-react";
import { TFunc } from "../i18n";
import ProgressSteps from "../components/ProgressSteps";
import StatusCard from "../components/StatusCard";

interface Props {
  t: TFunc;
  env?: any;
  modelInput: Record<string, any>;
  result?: Record<string, any>;
  onNavigate: (page: string) => void;
}

export default function HomePage({ t, env, modelInput, result, onNavigate }: Props) {
  const cards = [
    { title: t("home.env"), ok: env?.summary?.ok, active: Boolean(env), detail: env ? `${env.summary.errors.length} errors / ${env.summary.warnings.length} warnings` : t("home.notChecked") },
    { title: t("home.model"), ok: Boolean(modelInput.pt_path), detail: modelInput.pt_path || t("home.notSelected") },
    { title: t("home.yaml"), ok: Boolean(modelInput.data_yaml_path || modelInput.manual_classes?.length), detail: modelInput.data_yaml_path || t("home.manualClass") },
    { title: t("home.calib"), ok: Boolean(modelInput.calibration_dir), detail: modelInput.calibration_dir || t("home.notSelected") },
    { title: t("home.onnx"), ok: Boolean(result?.onnx_path), detail: result?.onnx_path || t("home.waitConvert") },
    { title: t("home.bin"), ok: Boolean(result?.bin_path), detail: result?.bin_path || t("home.waitQuant") },
    { title: t("home.report"), ok: Boolean(result?.deploy_report_path), detail: result?.deploy_report_path || t("home.waitReport") }
  ];

  const steps = [
    { name: t("home.step1"), status: env ? (env.summary.ok ? "success" : "warning") : "waiting" },
    { name: t("home.step2"), status: env?.summary?.ok ? "success" : "waiting" },
    { name: t("home.step3"), status: modelInput.pt_path ? "success" : "waiting" },
    { name: t("home.step4"), status: modelInput.calibration_dir && (modelInput.data_yaml_path || modelInput.manual_classes?.length) ? "success" : "waiting" },
    { name: t("home.step5"), status: result?.bin_path ? "success" : "waiting" },
    { name: t("home.step6"), status: result?.deploy_report_path ? "success" : "waiting" }
  ];

  return (
    <div className="page">
      <div className="page-header hero-header">
        <div>
          <h1>{t("home.title")}</h1>
          <p>{t("home.subtitle")}</p>
        </div>
        <button className="primary-action" onClick={() => onNavigate("env")}>
          {t("home.startEnv")}
          <ArrowRight size={18} />
        </button>
      </div>

      <ProgressSteps steps={steps} />

      <div className="status-grid">
        {cards.map((card) => (
          <StatusCard
            key={card.title}
            title={card.title}
            detail={card.detail}
            level={card.ok ? "ok" : card.active === false ? "idle" : "warn"}
          />
        ))}
      </div>
    </div>
  );
}
