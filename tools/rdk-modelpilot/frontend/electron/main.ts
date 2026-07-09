import { app, BrowserWindow, Menu, shell } from "electron";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;
const currentFile = fileURLToPath(import.meta.url);
const currentDir = path.dirname(currentFile);

function projectRoot(): string {
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.resolve(currentDir, "..", "..");
}

function startBackend(): void {
  const root = projectRoot();
  const packagedBackend = path.join(root, "backend", "rdk-modelpilot-backend.exe");
  const backendMain = path.join(root, "backend", "main.py");
  if (!fs.existsSync(packagedBackend) && !fs.existsSync(backendMain)) {
    return;
  }
  const command = fs.existsSync(packagedBackend) ? packagedBackend : "python";
  const args = fs.existsSync(packagedBackend) ? [] : [backendMain];
  backendProcess = spawn(command, args, {
    cwd: root,
    stdio: "pipe",
    windowsHide: true
  });
  const logDir = path.join(root, "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(logDir, "electron_backend.log");
  const writeLog = (chunk: Buffer) => fs.appendFileSync(logFile, chunk);
  backendProcess.stdout.on("data", writeLog);
  backendProcess.stderr.on("data", writeLog);
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1080,
    minHeight: 720,
    title: "RDK ModelPilot",
    backgroundColor: "#f5f7fb",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(path.join(currentDir, "..", "dist", "index.html"));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  startBackend();
  createWindow();
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
