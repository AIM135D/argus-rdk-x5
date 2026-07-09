import { ExternalLink, FolderOpen } from "lucide-react";
import { openPath } from "../api";
import { TFunc } from "../i18n";
import StatusCard from "../components/StatusCard";

interface Props {
  t: TFunc;
  result?: Record<string, any>;
}

function PathRow({ label, path }: { label: string; path?: string }) {
  if (!path) return <StatusCard title={label} detail="未生成" level="idle" />;
  return (
    <div className="path-row">
      <div>
        <strong>{label}</strong>
        <span>{path}</span>
      </div>
      <button title="打开" onClick={() => openPath(path)}>
        <ExternalLink size={16} />
      </button>
    </div>
  );
}

export default function ResultPage({ t, result }: Props) {
  if (!result) {
    return (
      <div className="page">
        <h1>{t("result.title")}</h1>
        <StatusCard title={t("result.title")} detail={t("result.empty")} level="idle" />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{t("result.title")}</h1>
          <p>{result.ok ? t("result.done") : t("result.partial")}</p>
        </div>
        {result.task_dir ? (
          <button className="primary-action" onClick={() => openPath(result.task_dir)}>
            <FolderOpen size={17} />
            {t("result.openFolder")}
          </button>
        ) : null}
      </div>
      <div className="paths-list">
        <PathRow label="ONNX 路径" path={result.onnx_path || result.export?.onnx_path} />
        <PathRow label="BIN 路径" path={result.bin_path || result.quant?.bin_path} />
        <PathRow label="deploy_config.py" path={result.deploy_config_path || result.deploy_config?.deploy_config_path} />
        <PathRow label="deploy_report.md" path={result.deploy_report_path || result.report?.deploy_report_path} />
        <PathRow label="env_check_report.md" path={result.env_check_report_path} />
        <PathRow label="calibration_report.md" path={result.calibration_report_path || result.calibration?.report_path} />
        <PathRow label="onnx_structure_report.md" path={result.onnx_structure_report_path || result.onnx_check?.report_path} />
      </div>
    </div>
  );
}
