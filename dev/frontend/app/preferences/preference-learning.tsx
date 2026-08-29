"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import styles from "@/app/product-flow.module.css";
import {
  completePreferenceLearning,
  getNextPreferencePage,
  recordPreference,
} from "@/lib/api-client";
import type { PreferenceEntry, PreferencePage } from "@/lib/api-contract";

const CATEGORY_LABELS: Record<PreferenceEntry["category"], string> = {
  food: "Food",
  drinks_party: "Drinks & nightlife",
  culture: "Culture",
  nature: "Nature",
};

export function PreferenceLearning({ itineraryId }: { itineraryId: string }) {
  const router = useRouter();
  const [page, setPage] = useState<PreferencePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadNext = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getNextPreferencePage(itineraryId);
      if (next) {
        setPage(next);
        setLoading(false);
        return;
      }
      await completePreferenceLearning(itineraryId);
      router.replace(`/creating?id=${encodeURIComponent(itineraryId)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load activities.");
      setLoading(false);
    }
  }, [itineraryId, router]);

  useEffect(() => {
    let cancelled = false;
    getNextPreferencePage(itineraryId)
      .then(async (next) => {
        if (cancelled) return;
        if (next) {
          setPage(next);
          setLoading(false);
          return;
        }
        await completePreferenceLearning(itineraryId);
        if (!cancelled) router.replace(`/creating?id=${encodeURIComponent(itineraryId)}`);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Could not load activities.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itineraryId, router]);

  async function choose(entry: PreferenceEntry, decision: "like" | "dislike") {
    if (!page || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (page.layout === "pair") {
        await Promise.all(
          page.entries.map((candidate) =>
            recordPreference(
              itineraryId,
              candidate.id,
              candidate.id === entry.id ? "like" : "dislike",
            ),
          ),
        );
      } else {
        await recordPreference(itineraryId, entry.id, decision);
      }
      await loadNext();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that choice.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.preferenceShell}>
      <section className={styles.preferencePanel} aria-busy={loading || submitting}>
        <header className={styles.preferenceHeader}>
          <p className={styles.eyebrow}>
            {page?.source === "adaptive" ? "One last question" : `Round ${page?.position ?? 1} of 3`}
          </p>
          <h1>{page?.layout === "single" ? "Would this fit your day?" : "Which feels more like you?"}</h1>
          <p>
            {page?.source === "adaptive"
              ? "This choice fine-tunes the categories we learned from your first three answers."
              : "Choose one activity from each pair. We’ll use all three choices to shape your day."}
          </p>
        </header>

        {loading && !page ? <p className={styles.loadingMessage}>Finding two good alternatives…</p> : null}

        {page ? (
          <div className={`${styles.activityGrid} ${page.layout === "single" ? styles.singleGrid : ""}`}>
            {page.entries.map((entry) => (
              <article className={styles.activityCard} key={entry.id}>
                {/* Activity image URLs come from the backend catalog and can use arbitrary hosts. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt="" className={styles.activityImage} src={entry.image_link} />
                <div className={styles.activityCopy}>
                  <p className={styles.category}>{CATEGORY_LABELS[entry.category] ?? entry.category}</p>
                  <h2>{entry.name}</h2>
                  <p>{entry.description}</p>
                  {page.layout === "pair" ? (
                    <button disabled={submitting} onClick={() => choose(entry, "like")} type="button">
                      Choose this
                    </button>
                  ) : (
                    <div className={styles.singleActions}>
                      <button disabled={submitting} onClick={() => choose(entry, "like")} type="button">
                        Yes, add this
                      </button>
                      <button className={styles.secondaryButton} disabled={submitting} onClick={() => choose(entry, "dislike")} type="button">
                        Not for me
                      </button>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {error ? (
          <div className={styles.flowError} role="alert">
            <p>{error}</p>
            <button onClick={() => void loadNext()} type="button">Try again</button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
