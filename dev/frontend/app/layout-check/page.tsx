import styles from "@/app/product-flow.module.css";

const LONG_ENTRY =
  "I spent a quiet hour at the activity, moving through its carefully made rooms while daylight settled softly across the stone. The surrounding streets continued at their ordinary pace outside. I paused to notice the small details, the changing sounds, and the way each space opened into the next without insisting on a single route. It felt considered rather than theatrical, and I stayed long enough for the place to set the rhythm of the afternoon before returning to the city.";

export default function LayoutCheckPage() {
  return (
    <main style={{ display: "grid", height: "100svh", placeItems: "center" }}>
      <article
        className={`${styles.preferenceJournalFace} ${styles.preferenceJournalFaceWithPhoto}`}
        style={{
          aspectRatio: "5 / 7",
          backgroundImage: "url(/journal-page-background.jpg)",
          width:
            "max(80px, min(calc((100vw - 32px) / 2), calc((100svh - 40px) / 1.4)))",
        }}
      >
        <figure className={styles.preferencePhoto}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="Travel inspiration" src="/journal-page-background.jpg" />
        </figure>
        <div className={styles.preferenceFaceCopy}>
          <p className={styles.category}>Neighbourhoods</p>
          <h2>A long afternoon discovering the old city</h2>
          <p>{LONG_ENTRY}</p>
        </div>
        <span aria-hidden="true" className={styles.preferenceFacePageNumber}>
          01
        </span>
      </article>
    </main>
  );
}
