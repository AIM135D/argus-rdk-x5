/// <reference types="vite/client" />

interface Window {
  rdkModelPilot?: {
    getPathForFile(file: File): string;
    selectPath(options: { directory: boolean; accept?: string }): Promise<string>;
  };
}
