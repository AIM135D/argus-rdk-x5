const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765/api";

export type ApiResult = Record<string, any>;

async function request<T = ApiResult>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response | undefined;
  let networkError: unknown;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      response = await fetch(`${API_BASE}${path}`, {
        headers: {
          "Content-Type": "application/json",
          ...(options.headers ?? {})
        },
        ...options
      });
      break;
    } catch (error) {
      networkError = error;
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
  }
  if (!response) {
    throw networkError instanceof Error ? networkError : new Error("RDK ModelPilot backend is unavailable");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function getConfig() {
  return request("/config");
}

export function saveConfig(config: Record<string, any>) {
  return request("/config", {
    method: "POST",
    body: JSON.stringify({ config })
  });
}

export function checkEnv() {
  return request("/env/check");
}

export function installEnv() {
  return request("/env/install", { method: "POST", body: JSON.stringify({}) });
}

export function getJob(jobId: string) {
  return request(`/jobs/${jobId}`);
}

export function inspectModel(payload: Record<string, any>) {
  return request("/model/inspect", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function checkCalibration(payload: Record<string, any>) {
  return request("/calibration/check", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runConvert(payload: Record<string, any>) {
  return request("/convert/run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getTaskStatus(path: string) {
  return request(`/task/status?path=${encodeURIComponent(path)}`);
}

export function readLog(path: string, maxChars = 40000) {
  return request(`/logs/read?path=${encodeURIComponent(path)}&max_chars=${maxChars}`);
}

export function openPath(path: string) {
  return request("/open-path", {
    method: "POST",
    body: JSON.stringify({ path })
  });
}
