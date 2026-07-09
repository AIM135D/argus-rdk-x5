import { CheckCircle2, Home, PlayCircle, Settings, SlidersHorizontal, TerminalSquare, UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getConfig, saveConfig } from "./api";
import { Lang, makeT } from "./i18n";
import ConvertPage from "./pages/ConvertPage";
import EnvCheckPage from "./pages/EnvCheckPage";
import HomePage from "./pages/HomePage";
import ModelInputPage from "./pages/ModelInputPage";
import ResultPage from "./pages/ResultPage";
import SettingsPage from "./pages/SettingsPage";

type PageKey = "home" | "env" | "model" | "convert" | "result" | "settings";

const NAV = [
  { key: "home", labelKey: "nav.home", icon: Home },
  { key: "env", labelKey: "nav.env", icon: TerminalSquare },
  { key: "model", labelKey: "nav.model", icon: UploadCloud },
  { key: "convert", labelKey: "nav.convert", icon: PlayCircle },
  { key: "result", labelKey: "nav.result", icon: CheckCircle2 },
  { key: "settings", labelKey: "nav.settings", icon: SlidersHorizontal }
] as const;

export default function App() {
  const [page, setPage] = useState<PageKey>("home");
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem("rdk-modelpilot-lang") as Lang) || "zh");
  const t = useMemo(() => makeT(lang), [lang]);
  const [config, setConfig] = useState<Record<string, any>>({});
  const [paths, setPaths] = useState<Record<string, any>>();
  const [env, setEnv] = useState<any>();
  const [modelInput, setModelInput] = useState<Record<string, any>>({
    pt_path: "",
    data_yaml_path: "",
    calibration_dir: "",
    output_dir: "",
    manual_classes: ["person", "helmet", "reflective_vest"],
    classText: "0 person\n1 helmet\n2 reflective_vest"
  });
  const [result, setResult] = useState<Record<string, any>>();

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    localStorage.setItem("rdk-modelpilot-lang", lang);
  }, [lang]);

  useEffect(() => {
    getConfig().then((payload) => {
      setConfig(payload.config);
      setPaths(payload.paths);
      setModelInput((current) => ({ ...current, output_dir: payload.config.output_dir }));
    });
  }, []);

  const handleSaveConfig = async (nextConfig: Record<string, any>) => {
    const payload = await saveConfig(nextConfig);
    setConfig(payload.config);
    setPaths(payload.paths);
  };

  const renderPage = () => {
    if (page === "home") return <HomePage t={t} env={env} modelInput={modelInput} result={result} onNavigate={(next) => setPage(next as PageKey)} />;
    if (page === "env") return <EnvCheckPage t={t} env={env} onEnv={setEnv} />;
    if (page === "model") return <ModelInputPage t={t} modelInput={modelInput} onChange={setModelInput} />;
    if (page === "convert") return <ConvertPage t={t} modelInput={modelInput} onResult={setResult} />;
    if (page === "result") return <ResultPage t={t} result={result} />;
    return <SettingsPage t={t} config={config} paths={paths} onSave={handleSaveConfig} />;
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <strong>RDK ModelPilot</strong>
            <span>X5 Deploy Kit</span>
          </div>
        </div>
        <nav>
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.key} className={page === item.key ? "active" : ""} onClick={() => setPage(item.key)}>
                <Icon size={18} />
                {t(item.labelKey)}
              </button>
            );
          })}
        </nav>
        <div className="language-switcher">
          <span>{t("lang.label")}</span>
          <select value={lang} onChange={(event) => setLang(event.target.value as Lang)}>
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
        </div>
        <button className="settings-link" onClick={() => setPage("settings")}>
          <Settings size={17} />
          {t("nav.config")}
        </button>
      </aside>
      <main>{renderPage()}</main>
    </div>
  );
}
