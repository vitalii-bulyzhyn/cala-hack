"use client";

import { useCallback, useEffect, useState } from "react";

import type { BackendHealth } from "@/lib/backend";

type ConnectionState =
  | { phase: "checking" }
  | { phase: "ready"; health: BackendHealth }
  | { phase: "unavailable"; health?: BackendHealth };

const REFRESH_INTERVAL_MS = 30_000;

function isBackendHealth(value: unknown): value is BackendHealth {
  if (!value || typeof value !== "object") {
    return false;
  }

  const health = value as Partial<BackendHealth>;

  return (
    typeof health.connected === "boolean" &&
    (health.state === "ready" || health.state === "unavailable") &&
    typeof health.checkedAt === "string" &&
    typeof health.responseTimeMs === "number"
  );
}

async function requestBackendHealth(): Promise<ConnectionState> {
  try {
    const response = await fetch("/api/backend-health", {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });
    const payload: unknown = await response.json();

    if (!isBackendHealth(payload)) {
      return { phase: "unavailable" };
    }

    return payload.connected
      ? { phase: "ready", health: payload }
      : { phase: "unavailable", health: payload };
  } catch {
    return { phase: "unavailable" };
  }
}

export function BackendStatus() {
  const [connection, setConnection] = useState<ConnectionState>({
    phase: "checking",
  });

  const refresh = useCallback(async (showCheckingState = true) => {
    if (showCheckingState) {
      setConnection({ phase: "checking" });
    }

    setConnection(await requestBackendHealth());
  }, []);

  useEffect(() => {
    let active = true;

    const poll = async () => {
      const nextConnection = await requestBackendHealth();

      if (active) {
        setConnection(nextConnection);
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, REFRESH_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const isChecking = connection.phase === "checking";
  const isReady = connection.phase === "ready";
  const checkedAt =
    connection.phase === "checking" ? undefined : connection.health?.checkedAt;

  return (
    <section className="connection" aria-labelledby="connection-title">
      <div className="connection__heading">
        <div>
          <p className="eyebrow">Local connection</p>
          <h2 id="connection-title">Backend status</h2>
        </div>
        <span
          className={`status-dot status-dot--${connection.phase}`}
          aria-hidden="true"
        />
      </div>

      <div className="connection__result" role="status" aria-live="polite">
        <strong>
          {isChecking
            ? "Checking the API…"
            : isReady
              ? "Backend connected"
              : "Backend unavailable"}
        </strong>
        <p>
          {isChecking
            ? "Looking for the local FastAPI service."
            : isReady
              ? `Ready in ${connection.health.responseTimeMs} ms.`
              : "Start the local stack, then try again."}
        </p>
        {checkedAt ? (
          <small>
            Last checked{" "}
            <time dateTime={checkedAt}>
              {new Intl.DateTimeFormat(undefined, {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              }).format(new Date(checkedAt))}
            </time>
          </small>
        ) : null}
      </div>

      <button
        className="text-button"
        type="button"
        disabled={isChecking}
        onClick={() => void refresh()}
      >
        Check again
      </button>
    </section>
  );
}
