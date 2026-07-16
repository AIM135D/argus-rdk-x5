import { contextBridge, ipcRenderer, webUtils } from "electron";

contextBridge.exposeInMainWorld("rdkModelPilot", {
  getPathForFile(file: File): string {
    return webUtils.getPathForFile(file);
  },
  selectPath(options: { directory: boolean; accept?: string }): Promise<string> {
    return ipcRenderer.invoke("select-path", options);
  }
});
