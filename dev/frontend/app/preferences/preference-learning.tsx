"use client";

import { Book } from "@gfazioli/mantine-book";
import { useElementSize } from "@mantine/hooks";
import { IconThumbDown, IconThumbUp } from "@tabler/icons-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import journalStyles from "@/app/journal-demo/journal-demo.module.css";
import styles from "@/app/product-flow.module.css";
import {
  completePreferenceLearning,
  getNextPreferencePage,
  getPreferencePages,
  recordPreference,
} from "@/lib/api-client";
import type { PreferenceEntry, PreferencePage } from "@/lib/api-contract";

const LEFT_PAGE_BACKGROUND = "/journal-left-page-background.jpg";
const RIGHT_PAGE_BACKGROUND = "/journal-page-background.jpg";
const PAGE_ASPECT_RATIO = 7 / 5;
const MIN_PAGE_WIDTH = 80;
const BOOK_SIDE_CLEARANCE = 32;
const BOOK_VERTICAL_CLEARANCE = 40;

const CATEGORY_LABELS: Record<PreferenceEntry["category"], string> = {
  food: "Food",
  drinks_party: "Drinks & nightlife",
  culture: "Culture",
  nature: "Nature",
};

type IssuedEntry = PreferenceEntry & {
  source: PreferencePage["source"];
};

type PreferenceFaceProps = {
  entry: IssuedEntry;
  pageNumber: number;
};

function PreferenceFace({ entry, pageNumber }: PreferenceFaceProps) {
  const background =
    pageNumber % 2 === 1 ? RIGHT_PAGE_BACKGROUND : LEFT_PAGE_BACKGROUND;

  return (
    <article
      aria-label={`Preference journal page ${pageNumber}: ${entry.name}`}
      className={`${styles.preferenceJournalFace} ${
        pageNumber % 2 === 1
          ? styles.preferenceRightFace
          : styles.preferenceLeftFace
      }`}
      style={{ backgroundImage: `url(${background})` }}
    >
      <div className={styles.preferenceFaceContent}>
        <div className={styles.preferenceFaceCopy}>
          <h2>{entry.name}</h2>
          <p>{entry.description}</p>
        </div>

        <figure className={styles.preferenceIllustration}>
          <span aria-hidden="true" className={styles.preferenceTape} />
          <span className={styles.preferenceImageFrame}>
            {/* Activity image URLs are supplied by the backend catalog. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              alt={`${entry.name} travel inspiration`}
              crossOrigin="anonymous"
              draggable={false}
              src={entry.image_link}
            />
          </span>
          <figcaption>
            {CATEGORY_LABELS[entry.category] ?? entry.category}
          </figcaption>
        </figure>
      </div>
      <span aria-hidden="true" className={styles.preferenceFacePageNumber}>
        {String(pageNumber).padStart(2, "0")}
      </span>
    </article>
  );
}

function EmptyPreferenceFace() {
  return (
    <div
      aria-hidden="true"
      className={styles.preferenceJournalFace}
      style={{ backgroundImage: `url(${LEFT_PAGE_BACKGROUND})` }}
    />
  );
}

type PreferenceRatingControlsProps = {
  entry: IssuedEntry;
  onRate: (decision: "like" | "dislike") => void;
  submitting: boolean;
};

function PreferenceRatingControls({
  entry,
  onRate,
  submitting,
}: PreferenceRatingControlsProps) {
  return (
    <div
      aria-label={`Your preference for ${entry.name}`}
      className={styles.preferenceBookRatingControls}
      onPointerDown={(event) => event.stopPropagation()}
      role="group"
    >
      <button
        aria-label={`Like ${entry.name}`}
        aria-pressed={entry.decision === "like"}
        className={styles.preferenceVoteButton}
        disabled={submitting}
        onClick={() => onRate("like")}
        title="Like"
        type="button"
      >
        <IconThumbUp aria-hidden="true" size={24} stroke={1.8} />
      </button>
      <button
        aria-label={`Dislike ${entry.name}`}
        aria-pressed={entry.decision === "dislike"}
        className={styles.preferenceVoteButton}
        disabled={submitting}
        onClick={() => onRate("dislike")}
        title="Not for me"
        type="button"
      >
        <IconThumbDown aria-hidden="true" size={24} stroke={1.8} />
      </button>
    </div>
  );
}

function terminalBookPage(totalFaces: number) {
  if (totalFaces <= 1) return 0;
  return totalFaces % 2 === 0 ? totalFaces - 1 : totalFaces - 2;
}

function previousBookPage(currentPage: number) {
  return currentPage <= 1 ? 0 : currentPage - 2;
}

function nextBookPage(currentPage: number, terminalPage: number) {
  if (currentPage === 0) return Math.min(1, terminalPage);
  return Math.min(terminalPage, currentPage + 2);
}

function visibleEntryIndexes(
  currentPage: number,
  totalFaces: number,
): readonly [number | null, number | null] {
  if (currentPage === 0) return [null, 0];

  const terminalPage = terminalBookPage(totalFaces);
  if (currentPage >= terminalPage && totalFaces % 2 === 0) {
    return [totalFaces - 1, null];
  }

  return [currentPage, Math.min(currentPage + 1, totalFaces - 1)];
}

function visiblePageLabel(currentPage: number, totalFaces: number) {
  const [left, right] = visibleEntryIndexes(currentPage, totalFaces);
  const visible = [left, right]
    .filter((index): index is number => index !== null)
    .map((index) => index + 1);

  if (visible.length === 1) return `Page ${visible[0]} of ${totalFaces}`;
  return `Pages ${visible[0]}–${visible[1]} of ${totalFaces}`;
}

function flattenEntries(pages: PreferencePage[]): IssuedEntry[] {
  return pages.flatMap((page) =>
    page.entries.map((entry) => ({ ...entry, source: page.source })),
  );
}

export function PreferenceLearning({ itineraryId }: { itineraryId: string }) {
  const router = useRouter();
  const [pages, setPages] = useState<PreferencePage[]>([]);
  const [bookPage, setBookPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submittingEntryId, setSubmittingEntryId] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    ref,
    width: availableWidth,
    height: availableHeight,
  } = useElementSize<HTMLDivElement>();

  const entries = useMemo(() => flattenEntries(pages), [pages]);
  const totalFaces = entries.length;
  const lastBookPage = terminalBookPage(totalFaces);
  const visibleEntries = visibleEntryIndexes(bookPage, totalFaces);
  const measuredWidth = availableWidth || MIN_PAGE_WIDTH * 2 + BOOK_SIDE_CLEARANCE;
  const measuredHeight =
    availableHeight || MIN_PAGE_WIDTH * PAGE_ASPECT_RATIO + BOOK_VERTICAL_CLEARANCE;
  const widthLimitedPage = (measuredWidth - BOOK_SIDE_CLEARANCE) / 2;
  const heightLimitedPage =
    (measuredHeight - BOOK_VERTICAL_CLEARANCE) / PAGE_ASPECT_RATIO;
  const pageWidth = Math.max(
    MIN_PAGE_WIDTH,
    Math.floor(Math.min(widthLimitedPage, heightLimitedPage)),
  );
  const pageHeight = Math.round(pageWidth * PAGE_ASPECT_RATIO);
  const sheets = useMemo(
    () =>
      Array.from({ length: Math.ceil(entries.length / 2) }, (_, index) => ({
        back: entries[index * 2 + 1],
        front: entries[index * 2],
      })),
    [entries],
  );

  const refreshIssuedPages = useCallback(async () => {
    const issuedPages = await getPreferencePages(itineraryId);
    setPages(issuedPages);
    return issuedPages;
  }, [itineraryId]);

  useEffect(() => {
    let cancelled = false;

    async function loadBook() {
      try {
        let issuedPages = await getPreferencePages(itineraryId);
        if (cancelled) return;

        if (issuedPages.length === 0) {
          const firstPage = await getNextPreferencePage(itineraryId);
          if (cancelled) return;

          if (!firstPage) {
            await completePreferenceLearning(itineraryId);
            if (!cancelled) {
              router.replace(`/creating?id=${encodeURIComponent(itineraryId)}`);
            }
            return;
          }

          issuedPages = await getPreferencePages(itineraryId);
        }

        if (cancelled) return;
        setPages(issuedPages);
        setLoading(false);
      } catch (caught) {
        if (cancelled) return;
        setError(
          caught instanceof Error ? caught.message : "Could not load activities.",
        );
        setLoading(false);
      }
    }

    void loadBook();
    return () => {
      cancelled = true;
    };
  }, [itineraryId, router]);

  useEffect(() => {
    function handleArrowKey(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;

      const target = event.target;
      const isBookFocused =
        target instanceof Element &&
        Boolean(target.closest('[aria-roledescription="book"]'));

      if (isBookFocused || event.defaultPrevented) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setBookPage(previousBookPage);
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        setBookPage((currentPage) => nextBookPage(currentPage, lastBookPage));
      }
    }

    window.addEventListener("keydown", handleArrowKey);
    return () => window.removeEventListener("keydown", handleArrowKey);
  }, [lastBookPage]);

  async function rateEntry(
    entry: IssuedEntry,
    decision: "like" | "dislike",
  ) {
    if (submittingEntryId) return;
    setSubmittingEntryId(entry.id);
    setError(null);

    try {
      await recordPreference(itineraryId, entry.id, decision);
      await refreshIssuedPages();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save that choice.",
      );
    } finally {
      setSubmittingEntryId(null);
    }
  }

  async function finishLearning() {
    if (finishing) return;
    setFinishing(true);
    setError(null);
    try {
      await completePreferenceLearning(itineraryId);
      router.replace(`/creating?id=${encodeURIComponent(itineraryId)}`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not create your journal.",
      );
      setFinishing(false);
    }
  }

  function showNextPages() {
    if (bookPage === lastBookPage) {
      void finishLearning();
      return;
    }
    setBookPage((currentPage) => nextBookPage(currentPage, lastBookPage));
  }

  if (loading || totalFaces === 0) {
    return (
      <main className={journalStyles.demoShell}>
        <p className={styles.preferenceBookLoading} role="status">
          Opening your preference journal…
        </p>
      </main>
    );
  }

  return (
    <main className={journalStyles.demoShell}>
      <h1 className={journalStyles.visuallyHidden}>Which feels more like you?</h1>
      <section
        aria-busy={Boolean(submittingEntryId) || finishing}
        aria-keyshortcuts="ArrowLeft ArrowRight"
        aria-label="Travel preference journal"
        className={journalStyles.trialPanel}
      >
        <div className={journalStyles.controls}>
          <output aria-live="polite" className={journalStyles.pageStatus}>
            {visiblePageLabel(bookPage, totalFaces)}
          </output>

          <div className={journalStyles.buttonGroup}>
            <button
              className={journalStyles.pageButton}
              disabled={bookPage === 0 || finishing}
              onClick={() => setBookPage(previousBookPage)}
              type="button"
            >
              Previous
            </button>
            <button
              className={journalStyles.pageButton}
              disabled={finishing}
              onClick={showNextPages}
              type="button"
            >
              {bookPage === lastBookPage
                ? finishing
                  ? "Creating…"
                  : "Create journal"
                : "Next"}
            </button>
          </div>
        </div>

        <div className={journalStyles.bookViewport} ref={ref}>
          <Book
            align={{ horizontal: "start", vertical: "start" }}
            aria-label="Page-turning travel preference journal"
            className={journalStyles.book}
            flippingTime={700}
            height={pageHeight}
            mobileScrollSupport
            onPageChange={(nextPage) =>
              setBookPage(Math.min(nextPage, lastBookPage))
            }
            page={bookPage}
            pageBackground="#fffaf0"
            revealBackground="#d8c7a9"
            shadowOpacity={0.45}
            turnOrigin="bottom"
            variant="rounded"
            width={pageWidth}
          >
            {sheets.map((sheet, sheetIndex) => (
              <Book.Page key={`${sheet.front.id}-${sheet.back?.id ?? "empty"}`}>
                <Book.Page.Front>
                  <PreferenceFace
                    entry={sheet.front}
                    pageNumber={sheetIndex * 2 + 1}
                  />
                </Book.Page.Front>
                <Book.Page.Back>
                  {sheet.back ? (
                    <PreferenceFace
                      entry={sheet.back}
                      pageNumber={sheetIndex * 2 + 2}
                    />
                  ) : (
                    <EmptyPreferenceFace />
                  )}
                </Book.Page.Back>
              </Book.Page>
            ))}
          </Book>

          <div
            aria-label="Preferences for visible journal pages"
            className={journalStyles.ratingOverlay}
            style={{ height: pageHeight, width: pageWidth * 2 }}
          >
            {visibleEntries.map((entryIndex, index) => (
              <div className={journalStyles.ratingPage} key={index}>
                {entryIndex !== null && entries[entryIndex] ? (
                  <PreferenceRatingControls
                    entry={entries[entryIndex]}
                    onRate={(decision) =>
                      void rateEntry(entries[entryIndex], decision)
                    }
                    submitting={Boolean(submittingEntryId)}
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>

        {error ? (
          <div className={styles.preferenceBookError} role="alert">
            {error}
          </div>
        ) : null}
      </section>
    </main>
  );
}
