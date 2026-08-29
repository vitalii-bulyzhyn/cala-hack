import { DestinationForm } from "@/app/components/destination-form";
import styles from "@/app/journey-flow.module.css";

export default function Home() {
  return (
    <main className={`${styles.flowShell} ${styles.entryShell}`}>
      <section className={styles.flowContent} aria-labelledby="start-title">
        <h1 className={styles.visuallyHidden} id="start-title">
          Start a travel journal
        </h1>
        <DestinationForm />
      </section>
    </main>
  );
}
