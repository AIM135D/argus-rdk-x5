import { FileInput } from "lucide-react";
import { DragEvent, useRef } from "react";

interface Props {
  label: string;
  value: string;
  accept?: string;
  placeholder?: string;
  directory?: boolean;
  onPath: (path: string) => void;
}

function getElectronPath(file: File): string {
  const maybe = file as File & { path?: string };
  return maybe.path || file.name;
}

export default function FileDropZone({ label, value, accept, placeholder, directory = false, onPath }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) onPath(getElectronPath(file));
  };

  return (
    <div className="drop-group">
      <label>{label}</label>
      <div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={onDrop} onClick={() => inputRef.current?.click()}>
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
          if (file) onPath(getElectronPath(file));
        }}
        {...(directory ? ({ webkitdirectory: "true" } as any) : {})}
      />
      <input className="path-input" value={value} placeholder="Paste Windows absolute path / 粘贴 Windows 绝对路径" onChange={(event) => onPath(event.target.value)} />
    </div>
  );
}
