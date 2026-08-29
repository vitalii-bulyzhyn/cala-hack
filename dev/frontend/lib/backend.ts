import "server-only";

const DEFAULT_BACKEND_URL = "http://localhost:8000";
const BACKEND_HEALTH_PATH = "/api/v1/health/ready";
const BACKEND_TIMEOUT_MS = 3_000;

export type BackendHealth = {
  connected: boolean;
  state: "ready" | "unavailable";
  checkedAt: string;
  responseTimeMs: number;
};

function getBackendUrl(path: string): string {
  const baseUrl = (process.env.BACKEND_URL || DEFAULT_BACKEND_URL).replace(
    /\/+$/,
    "",
  );

  return `${baseUrl}${path}`;
}

export async function checkBackendHealth(): Promise<BackendHealth> {
  const startedAt = performance.now();

  try {
    const response = await fetch(getBackendUrl(BACKEND_HEALTH_PATH), {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });

    // Drain the small readiness response so the server runtime can reuse the
    // connection without coupling this boundary to the backend payload shape.
    await response.arrayBuffer();

    return {
      connected: response.ok,
      state: response.ok ? "ready" : "unavailable",
      checkedAt: new Date().toISOString(),
      responseTimeMs: Math.round(performance.now() - startedAt),
    };
  } catch {
    return {
      connected: false,
      state: "unavailable",
      checkedAt: new Date().toISOString(),
      responseTimeMs: Math.round(performance.now() - startedAt),
    };
  }
}
