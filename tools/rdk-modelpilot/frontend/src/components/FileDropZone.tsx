import { FileInput } from "lucide-react";
import { DragEvent, useRef, useState } from "react";

interface Props {
  label: string;
  value: string;
  accept?: string;
  placeholder?: string;
  directory?: boolean;
  onPath: (path: string) => void;
}

function getElectronPath(file: File): string {
  const bridgedPath = window.rdkModelPilot?.getPathForFile(file);
  if (bridgedPath) return bridgedPath;
  const maybe = file as File & { path?: string };
  return maybe.path || "";
}

export default function FileDropZone({ label, value, accept, placeholder, directory = false, onPath }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [pathError, setPathError] = useState("");

  const commitFile = (file: File) => {
    const resolvedPath = getElectronPath(file);
    if (!resolvedPath) {
      setPathError("无法读取完整文件路径，请使用桌面版的选择按钮重试。 / Unable to resolve the absolute path.");
      return;
    }
    setPathError("");
    onPath(resolvedPath);
  };

  const choosePath = async () => {
    if (!window.rdkModelPilot) {
      inputRef.current?.click();
      return;
    }
    const selectedPath = await window.rdkModelPilot.selectPath({ directory, accept });
    if (selectedPath) {
      setPathError("");
      onPath(selectedPath);
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) commitFile(file);
  };

  return (
    <div className="drop-group">
      <label>{label}</label>
      <div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={onDrop} onClick={choosePath}>
        <FileInput size={22} />
        <span>{value || placeholder || "Drop here or click to choose / 拖入或点击选择"}</span>
      </div>
      <input
        ref={inputRef}
        className="hidden-input"
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) commitFile(file);
        }}
        {...(directory ? ({ webkitdirectory: "true" } as any) : {})}
      />
      {pathError ? <div className="inline-error">{pathError}</div> : null}
      <input className="path-input" value={value} placeholder="Paste Windows absolute path / 粘贴 Windows 绝对路径" onChange={(event) => onPath(event.target.value)} />
    </div>
  );
}
