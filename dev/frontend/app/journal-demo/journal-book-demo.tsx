"use client";

import { Book } from "@gfazioli/mantine-book";
import { useElementSize } from "@mantine/hooks";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import styles from "@/app/journal-demo/journal-demo.module.css";

const LEFT_PAGE_BACKGROUND = "/journal-left-page-background.jpg";
const RIGHT_PAGE_BACKGROUND = "/journal-page-background.jpg";
const PAGE_ASPECT_RATIO = 7 / 5;
const MIN_PAGE_WIDTH = 80;
const BOOK_SIDE_CLEARANCE = 32;
const BOOK_VERTICAL_CLEARANCE = 40;

const faceContent = [
  {
    heading: "A slow morning",
    copy: "Coffee, a folded map, and the first notes for a day in the city.",
  },
  {
    heading: "First stop",
    copy: "A quiet lane gives the journal its opening sketch and first memory.",
  },
  {
    heading: "Market colours",
    copy: "Fruit crates, striped awnings, and small details worth keeping.",
  },
  {
    heading: "After lunch",
    copy: "The route bends toward the sea while the afternoon light softens.",
  },
  {
    heading: "Golden hour",
    copy: "One last overlook turns the city into layers of warm paper and ink.",
  },
  {
    heading: "End of the day",
    copy: "A final note closes the trial journal, ready for real itinerary data.",
  },
] as const;

const LAST_PAGE = faceContent.length - 1;

const sheets = Array.from({ length: faceContent.length / 2 }, (_, index) => ({
  front: faceContent[index * 2],
  back: faceContent[index * 2 + 1],
}));

type JournalFaceProps = {
  copy: string;
  destination: string;
  heading: string;
  pageNumber: number;
};

type PageRating = "like" | "dislike";

function JournalFace({
  copy,
  destination,
  heading,
  pageNumber,
}: JournalFaceProps) {
  const background = pageNumber % 2 === 1 ? RIGHT_PAGE_BACKGROUND : LEFT_PAGE_BACKGROUND;
  return (
    <article
      aria-label={`Journal page ${pageNumber} for ${destination}`}
      className={styles.journalFace}
      style={{ backgroundImage: `url(${background})` }}
    >
      <div className={styles.faceContent}>
        <p className={styles.faceKicker}>{destination} · field notes</p>
        <h2 className={styles.faceTitle}>{heading}</h2>
        <p className={styles.faceCopy}>{copy}</p>
      </div>
      <span aria-hidden="true" className={styles.pageNumber}>
        {String(pageNumber).padStart(2, "0")}
      </span>
    </article>
  );
}

function visiblePageLabel(page: number) {
  if (page === 0) {
    return `Page 1 of ${faceContent.length}`;
  }

  if (page >= faceContent.length - 1) {
    return `Page ${faceContent.length} of ${faceContent.length}`;
  }

  return `Pages ${page + 1}–${page + 2} of ${faceContent.length}`;
}

function visiblePageNumbers(currentPage: number) {
  if (currentPage === 0) {
    return [null, 1] as const;
  }

  if (currentPage >= faceContent.length - 1) {
    return [faceContent.length, null] as const;
  }

  return [currentPage + 1, currentPage + 2] as const;
}

function previousPage(currentPage: number) {
  if (currentPage <= 1) {
    return 0;
  }

  return currentPage - 2;
}

function nextPage(currentPage: number) {
  if (currentPage === 0) {
    return 1;
  }

  return Math.min(LAST_PAGE, currentPage + 2);
}

type PageRatingControlsProps = {
  onRate: (rating: PageRating) => void;
  pageNumber: number;
  rating?: PageRating;
};

function PageRatingControls({
  onRate,
  pageNumber,
  rating,
}: PageRatingControlsProps) {
  return (
    <div
      aria-label={`Preference for journal page ${pageNumber}`}
      className={styles.ratingControls}
      onPointerDown={(event) => event.stopPropagation()}
      role="group"
    >
      <button
        aria-pressed={rating === "like"}
        className={styles.ratingButton}
        onClick={() => onRate("like")}
        type="button"
      >
        <span aria-hidden="true">👍</span> Like
      </button>
      <button
        aria-pressed={rating === "dislike"}
        className={styles.ratingButton}
        onClick={() => onRate("dislike")}
        type="button"
      >
        <span aria-hidden="true">👎</span> Not for me
      </button>
    </div>
  );
}

type JournalBookDemoProps = {
  completionUrl?: string;
  destination?: string;
  stage?: "review" | "final";
};

export function JournalBookDemo({
  completionUrl,
  destination = "Barcelona",
  stage = "final",
}: JournalBookDemoProps) {
  const router = useRouter();
  const [page, setPage] = useState(0);
  const [ratings, setRatings] = useState<Partial<Record<number, PageRating>>>({});
  const {
    ref,
    width: availableWidth,
    height: availableHeight,
  } = useElementSize<HTMLDivElement>();
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
  const visiblePages = visiblePageNumbers(page);
  const isReview = stage === "review" && Boolean(completionUrl);

  useEffect(() => {
    function handleArrowKey(event: KeyboardEvent) {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey
      ) {
        return;
      }

      const target = event.target;
      const isBookFocused =
        target instanceof Element &&
        Boolean(target.closest('[aria-roledescription="book"]'));

      if (isBookFocused) {
        if (
          event.key === "ArrowRight" &&
          page === LAST_PAGE &&
          isReview &&
          completionUrl
        ) {
          event.preventDefault();
          router.push(completionUrl);
        }

        return;
      }

      if (event.defaultPrevented) {
        return;
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setPage(previousPage);
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();

        if (page === LAST_PAGE && isReview && completionUrl) {
          router.push(completionUrl);
        } else {
          setPage(nextPage);
        }
      }
    }

    window.addEventListener("keydown", handleArrowKey);
    return () => window.removeEventListener("keydown", handleArrowKey);
  }, [completionUrl, isReview, page, router]);

  function showPreviousPages() {
    setPage(previousPage);
  }

  function showNextPages() {
    if (page === LAST_PAGE && isReview && completionUrl) {
      router.push(completionUrl);
      return;
    }

    setPage(nextPage);
  }

  function ratePage(pageNumber: number, rating: PageRating) {
    setRatings((currentRatings) => ({
      ...currentRatings,
      [pageNumber]:
        currentRatings[pageNumber] === rating ? undefined : rating,
    }));
  }

  return (
    <section
      aria-keyshortcuts="ArrowLeft ArrowRight"
      aria-label={`Page-turning journal for ${destination}`}
      className={styles.trialPanel}
    >
      <div className={styles.controls}>
        <output aria-live="polite" className={styles.pageStatus}>
          {visiblePageLabel(page)}
        </output>

        <div className={styles.buttonGroup}>
          <button
            className={styles.pageButton}
            disabled={page === 0}
            onClick={showPreviousPages}
            type="button"
          >
            Previous
          </button>
          <button
            className={styles.pageButton}
            disabled={page === LAST_PAGE && !isReview}
            onClick={showNextPages}
            type="button"
          >
            {page === LAST_PAGE && isReview ? "Create journal" : "Next"}
          </button>
        </div>
      </div>

      <div className={styles.bookViewport} ref={ref}>
        <Book
          align={{ horizontal: "start", vertical: "start" }}
          aria-label={`Static-image journal for ${destination}`}
          className={styles.book}
          flippingTime={700}
          height={pageHeight}
          mobileScrollSupport
          onPageChange={setPage}
          page={page}
          pageBackground="#fffaf0"
          revealBackground="#d8c7a9"
          shadowOpacity={0.45}
          turnOrigin="bottom"
          variant="rounded"
          width={pageWidth}
        >
          {sheets.map((sheet, sheetIndex) => (
            <Book.Page key={sheetIndex}>
              <Book.Page.Front>
                <JournalFace
                  copy={sheet.front.copy}
                  destination={destination}
                  heading={sheet.front.heading}
                  pageNumber={sheetIndex * 2 + 1}
                />
              </Book.Page.Front>
              <Book.Page.Back>
                <JournalFace
                  copy={sheet.back.copy}
                  destination={destination}
                  heading={sheet.back.heading}
                  pageNumber={sheetIndex * 2 + 2}
                />
              </Book.Page.Back>
            </Book.Page>
          ))}
        </Book>

        {isReview ? (
          <div
            aria-label="Preferences for visible journal pages"
            className={styles.ratingOverlay}
            style={{ height: pageHeight, width: pageWidth * 2 }}
          >
            {visiblePages.map((pageNumber, index) => (
              <div className={styles.ratingPage} key={index}>
                {pageNumber ? (
                  <PageRatingControls
                    onRate={(rating) => ratePage(pageNumber, rating)}
                    pageNumber={pageNumber}
                    rating={ratings[pageNumber]}
                  />
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
