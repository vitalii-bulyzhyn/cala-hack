"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import styles from "@/app/product-flow.module.css";
import { getItinerary } from "@/lib/api-client";
import type { ItineraryResource } from "@/lib/api-contract";

export function JournalResult({ itineraryId }: { itineraryId: string }) {
  const [resource, setResource] = useState<ItineraryResource | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getItinerary(itineraryId).then(setResource).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load your journal.");
    });
  }, [itineraryId]);

  if (error) {
    return <main className={styles.resultShell}><p role="alert">{error}</p></main>;
  }
  if (!resource) {
    return <main className={styles.resultShell}><p>Opening your journal…</p></main>;
  }
  if (resource.status === "pending") {
    return (
      <main className={styles.resultShell}>
        <p>Your journal is still being made. <a href={`/creating?id=${encodeURIComponent(itineraryId)}`}>See progress</a></p>
      </main>
    );
  }
  if (resource.status === "fail" || !resource.result) {
    return (
      <main className={styles.resultShell}>
        <p role="alert">{resource.error?.message ?? "This journal could not be completed."}</p>
        <Link href="/">Start again</Link>
      </main>
    );
  }

  const result = resource.result;
  const isOfflineDemo = result.summary.includes("offline sample journal");
  return (
    <main className={styles.resultShell}>
      <article className={styles.resultJournal}>
        <div className={styles.resultSpread}>
          <header className={`${styles.resultHeader} ${styles.resultLeftPage}`}>
            <p className={styles.eyebrow}>{result.destination} · {result.planned_date}</p>
            <h1>{result.title}</h1>
            <p>{result.summary}</p>
          </header>

          <figure className={`${styles.heroFigure} ${styles.resultRightPage}`}>
            {isOfflineDemo ? (
              <div className={styles.offlineJournalMark}>
                <p className={styles.eyebrow}>Offline sample</p>
                <h2>{result.destination}</h2>
                <p>Ready to test — no provider credentials used.</p>
              </div>
            ) : (
              <>
                {/* The absolute, app-owned media URL is supplied by the backend. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt={result.journal_image.alt_text} src={result.journal_image.url} />
              </>
            )}
            <figcaption>
              {isOfflineDemo
                ? "Offline demo journal page — use the sample place details below to test the flow."
                : "Generated illustration — use the place details below for your plan."}
            </figcaption>
          </figure>
        </div>

        <section aria-labelledby="day-plan-title" className={styles.placeSection}>
          <div>
            <p className={styles.eyebrow}>One day · {result.destination_timezone}</p>
            <h2 id="day-plan-title">Your day, in order</h2>
          </div>
          <ol className={styles.placeList}>
            {result.places.map((place) => (
              <li className={styles.placeCard} key={place.id}>
                <time>{place.start_time}–{place.end_time}</time>
                <div>
                  <p className={styles.category}>{place.category}</p>
                  <h3>{place.name}</h3>
                  <p>{place.description}</p>
                  <p className={styles.reason}>{place.reason_to_visit}</p>
                  {place.location?.address ? <address>{place.location.address}</address> : null}
                  <div className={styles.placeLinks}>
                    {place.links.map((link) => (
                      <a href={link.url} key={`${place.id}-${link.kind}-${link.url}`} rel="noreferrer" target="_blank">
                        {link.label} <span>↗</span>
                      </a>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <footer className={styles.resultFooter}>
          <p>Opening hours and availability can change. Verify time-sensitive details before you go.</p>
          <Link href="/">Plan another day</Link>
        </footer>
      </article>
    </main>
  );
}
