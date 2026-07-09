import ConfigEditor from "../components/ConfigEditor";
import StatusCard from "../components/StatusCard";
import { TFunc } from "../i18n";

interface Props {
  t: TFunc;
  config: Record<string, any>;
  paths?: Record<string, any>;
  onSave: (config: Record<string, any>) => Promise<void>;
}

export default function SettingsPage({ t, config, paths, onSave }: Props) {
  return (
    <div className="page two-column">
      <section>
        <div className="page-header compact-header">
          <div>
            <h1>{t("settings.title")}</h1>
            <p>{t("settings.subtitle")}</p>
          </div>
        </div>
        <ConfigEditor config={config} onSave={onSave} />
      </section>
      <aside className="side-panel">
        <h2>{t("settings.pathCheck")}</h2>
        {paths
          ? Object.entries(paths)
              .filter(([key]) => key !== "derived")
              .map(([key, item]: [string, any]) => (
                <StatusCard key={key} title={key} detail={item.path} level={item.exists ? "ok" : "warn"} />
              ))
          : null}
        {paths?.derived ? (
          <div className="derived-box">
            <h3>{t("settings.pathConvert")}</h3>
            {Object.entries(paths.derived).map(([key, value]) => (
              <div key={key}>
                <strong>{key}</strong>
                <span>{String(value)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </aside>
    </div>
  );
}
