"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import styles from "@/app/product-flow.module.css";
import { getItineraryStatus } from "@/lib/api-client";
import type { ItineraryResource } from "@/lib/api-contract";

const POLL_MS = 2_000;
const STAGE_COPY: Record<NonNullable<ItineraryResource["stage"]>, string> = {
  learning_preferences: "Learning what kind of day fits you",
  queued: "Preparing your journal",
  researching: "Finding grounded places",
  planning: "Arranging the day",
  illustrating: "Drawing your journal",
};

export function GenerationStatus({ itineraryId }: { itineraryId: string }) {
  const router = useRouter();
  const [stage, setStage] = useState<ItineraryResource["stage"]>("queued");
  const [error, setError] = useState<ItineraryResource["error"] | null>(null);
  const [transportError, setTransportError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const { resource, retryAfterMs } = await getItineraryStatus(itineraryId);
        if (stopped) return;
        setTransportError(null);
        if (resource.status === "done") {
          router.replace(`/journal?id=${encodeURIComponent(itineraryId)}`);
          return;
        }
        if (resource.status === "fail") {
          setError(resource.error);
          return;
        }
        setStage(resource.stage);
        timer = setTimeout(poll, retryAfterMs);
      } catch (caught) {
        if (stopped) return;
        setTransportError(
          caught instanceof Error ? caught.message : "The status check was interrupted.",
        );
        timer = setTimeout(poll, POLL_MS * 2);
      }
    }

    timer = setTimeout(poll, 0);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [itineraryId, router]);

  if (error) {
    return (
      <div className={styles.generationFailure} role="alert">
        <p className={styles.eyebrow}>Journal not created</p>
        <h1>We hit a snag.</h1>
        <p>{error.message}</p>
        <p className={styles.requestId}>Reference: {error.request_id}</p>
        <Link href="/">Choose another city</Link>
      </div>
    );
  }

  return (
    <div aria-live="polite" className={styles.generationStatus} role="status">
      <p className={styles.eyebrow}>Making your day</p>
      <h1>{stage ? STAGE_COPY[stage] : "Preparing your journal"}</h1>
      <div aria-hidden="true" className={styles.inkLoader}><span /><span /><span /></div>
      {transportError ? <p className={styles.transportNote}>{transportError} Retrying…</p> : null}
    </div>
  );
}
