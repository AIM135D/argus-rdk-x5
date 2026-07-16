import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { inspectModel } from "../api";
import { TFunc } from "../i18n";
import FileDropZone from "../components/FileDropZone";
import StatusCard from "../components/StatusCard";

interface Props {
  t: TFunc;
  modelInput: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
}

function parseClasses(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^\d+\s+/, ""))
    .filter(Boolean);
}

export default function ModelInputPage({ t, modelInput, onChange }: Props) {
  const [classText, setClassText] = useState(modelInput.classText ?? "0 person\n1 helmet\n2 reflective_vest");
  const [inspect, setInspect] = useState<any>(null);
  const [error, setError] = useState("");
  const manualClasses = useMemo(() => parseClasses(classText), [classText]);
  const classLevel = manualClasses.length >= 1 && manualClasses.length <= 10 ? "ok" : "warn";

  const setField = (key: string, value: string) => {
    const next = { ...modelInput, [key]: value };
    onChange(next);
    setInspect(null);
    setError("");
  };

  const updateClassText = (value: string) => {
    const classes = parseClasses(value);
    setClassText(value);
    onChange({ ...modelInput, classText: value, manual_classes: classes });
    setInspect(null);
    setError("");
  };

  const runInspect = async () => {
    setError("");
    const payload: Record<string, any> = { ...modelInput, manual_classes: manualClasses, classText };
    onChange(payload);
    try {
      const result = await inspectModel(payload);
      setInspect(result);
      const yamlNames = result.data_yaml?.names ?? [];
      const resolvedYamlPath = result.data_yaml?.resolved_data_yaml_path ?? "";
      const nextPayload = {
        ...payload,
        data_yaml_path: resolvedYamlPath || payload.data_yaml_path,
        calibration_dir: !modelInput.calibration_dir && result.auto_calibration_dir ? result.auto_calibration_dir : payload.calibration_dir,
        manual_classes: yamlNames.length ? yamlNames : manualClasses,
        classText: yamlNames.length ? yamlNames.map((name: string, index: number) => `${index} ${name}`).join("\n") : classText
      };
      if (yamlNames.length) {
        setClassText(nextPayload.classText);
      }
      onChange(nextPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="page two-column">
      <section>
        <div className="page-header compact-header hero-header">
          <div>
            <h1>{t("model.title")}</h1>
            <p>{t("model.subtitle")}</p>
          </div>
          <button className="primary-action" onClick={runInspect}>
            <Search size={17} />
            {t("model.inspect")}
          </button>
        </div>

        {error ? <div className="inline-error">{error}</div> : null}
        <FileDropZone label={t("model.pt")} accept=".pt" value={modelInput.pt_path ?? ""} onPath={(path) => setField("pt_path", path)} />
        <FileDropZone label={t("model.yaml")} accept=".yaml,.yml" value={modelInput.data_yaml_path ?? ""} onPath={(path) => setField("data_yaml_path", path)} />
        <FileDropZone label={t("model.calib")} directory value={modelInput.calibration_dir ?? ""} onPath={(path) => setField("calibration_dir", path)} />
        <FileDropZone label={t("model.output")} directory value={modelInput.output_dir ?? ""} onPath={(path) => setField("output_dir", path)} />

        <label className="form-row stacked">
          <span>{t("model.manual")}</span>
          <textarea value={classText} onChange={(event) => updateClassText(event.target.value)} rows={6} />
        </label>
      </section>

      <aside className="side-panel">
        <h2>{t("model.current")}</h2>
        <StatusCard title={t("model.classSupport")} detail={`${manualClasses.length || 0} / 1-10`} level={classLevel} />
        <StatusCard title={t("model.size")} detail="640 x 640" level="ok" />
        <StatusCard title={t("model.target")} detail="RDK X5 bayes-e" level="ok" />
        <StatusCard title={t("model.runtime")} detail="NV12" level="ok" />
        {inspect?.pt ? (
          <>
            <StatusCard title={t("model.fileName")} detail={inspect.pt.name} level="ok" />
            <StatusCard title={t("model.fileSize")} detail={`${inspect.pt.size_mb} MB`} level="idle" />
            <StatusCard title={t("model.modified")} detail={inspect.pt.modified} level="idle" />
            <StatusCard title={t("model.recoOnnx")} detail={inspect.recommended_onnx} level="idle" />
            <StatusCard title={t("model.recoBin")} detail={inspect.recommended_bin} level="idle" />
          </>
        ) : null}
        {inspect?.data_yaml ? (
          <div className="class-table">
            <h3>{t("model.classOrder")}</h3>
            <div>nc = {inspect.data_yaml.nc}</div>
            {inspect.data_yaml.resolved_data_yaml_path ? (
              <div className="inline-success">{t("model.yamlResolved")}: {inspect.data_yaml.resolved_data_yaml_path}</div>
            ) : null}
            {!inspect.data_yaml.names.length ? <div className="inline-error">{t("model.classMissing")}</div> : null}
            {inspect.data_yaml.validation?.errors?.length ? (
              <div className="inline-error">{inspect.data_yaml.validation.errors.join("; ")}</div>
            ) : null}
            {inspect.data_yaml.names.map((name: string, index: number) => (
              <div className="class-row" key={`${index}-${name}`}>
                <span>{index}</span>
                <strong>{name}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {inspect?.calibration_preview ? (
          <StatusCard
            title={t("model.calibPreview")}
            detail={
              inspect.calibration_preview.summary.errors.length
                ? `${inspect.calibration_preview.total_images} ${t("model.calibUnavailable")}`
                : inspect.calibration_preview.total_images < 20
                  ? `${inspect.calibration_preview.total_images} ${t("model.calibTestAllowed")}`
                  : `${inspect.calibration_preview.total_images} ${t("model.calibReady")}`
            }
            level={inspect.calibration_preview.summary.errors.length ? "error" : inspect.calibration_preview.summary.warnings.length ? "warn" : "ok"}
          />
        ) : null}
      </aside>
    </div>
  );
}
