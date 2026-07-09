import { Save } from "lucide-react";
import { useEffect, useState } from "react";

const FIELDS = [
  ["project_dir", "Project directory / 项目目录"],
  ["output_dir", "Output directory / 输出目录"],
  ["rdk_model_zoo_windows", "rdk_model_zoo Windows path / Windows 路径"],
  ["rdk_model_zoo_wsl", "rdk_model_zoo WSL path / WSL 路径"],
  ["export_script_windows", "export_monkey_patch.py Windows path"],
  ["export_script_wsl", "export_monkey_patch.py WSL path"],
  ["mapper_windows", "mapper.py Windows path"],
  ["mapper_wsl", "mapper.py WSL path"],
  ["conda_env", "Conda env name / Conda 环境名"],
  ["wsl_distro", "WSL distro / WSL 发行版"],
  ["docker_image", "Docker image / Docker 镜像"],
  ["default_imgsz", "Input size / 输入尺寸"],
  ["target", "Target / 目标平台"],
  ["runtime_input", "Runtime input / 运行时输入格式"]
];

interface Props {
  config: Record<string, any>;
  onSave: (config: Record<string, any>) => Promise<void>;
}

export default function ConfigEditor({ config, onSave }: Props) {
  const [draft, setDraft] = useState<Record<string, any>>(config);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(config), [config]);

  const update = (key: string, value: string) => {
    setDraft((current) => ({ ...current, [key]: key === "default_imgsz" ? Number(value) : value }));
  };

  return (
    <div className="config-editor">
      {FIELDS.map(([key, label]) => (
        <label className="form-row" key={key}>
          <span>{label}</span>
          <input value={draft[key] ?? ""} onChange={(event) => update(key, event.target.value)} />
        </label>
      ))}
      <label className="form-row">
        <span>Install policy / 自动安装策略</span>
        <select value={draft.install_mode ?? "AUTO"} onChange={(event) => update("install_mode", event.target.value)}>
          <option value="AUTO">AUTO</option>
          <option value="SAFE">SAFE</option>
          <option value="NO">NO</option>
        </select>
      </label>
      <button
        className="primary-action"
        disabled={saving}
        onClick={async () => {
          setSaving(true);
          try {
            await onSave(draft);
          } finally {
            setSaving(false);
          }
        }}
      >
        <Save size={17} />
        {saving ? "Saving / 保存中" : "Save Settings / 保存设置"}
      </button>
    </div>
  );
}
