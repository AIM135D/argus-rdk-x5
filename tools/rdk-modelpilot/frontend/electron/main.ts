import { app, BrowserWindow, dialog, ipcMain, Menu, shell } from "electron";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;
const currentFile = fileURLToPath(import.meta.url);
const currentDir = path.dirname(currentFile);

function registerIpcHandlers(): void {
  ipcMain.handle("select-path", async (_event, options: { directory?: boolean; accept?: string }) => {
    const directory = Boolean(options?.directory);
    const extensions = String(options?.accept ?? "")
      .split(",")
      .map((item) => item.trim().replace(/^\./, ""))
      .filter((item) => /^[a-z0-9]+$/i.test(item));
    const result = await dialog.showOpenDialog({
      properties: directory ? ["openDirectory"] : ["openFile"],
      filters: !directory && extensions.length ? [{ name: "Supported files", extensions }] : undefined
    });
    return result.canceled ? "" : result.filePaths[0] ?? "";
  });
}

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
  const dataDir = path.join(app.getPath("userData"), "runtime");
  fs.mkdirSync(dataDir, { recursive: true });
  backendProcess = spawn(command, args, {
    cwd: root,
    stdio: "pipe",
    windowsHide: true,
    env: {
      ...process.env,
      RDK_MODELPILOT_DATA_DIR: dataDir,
      RDK_MODELPILOT_RESOURCE_DIR: root
    }
  });
  const logDir = path.join(dataDir, "logs");
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
      contextIsolation: true,
      preload: path.join(currentDir, "preload.cjs")
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
  registerIpcHandlers();
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
