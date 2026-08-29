import type { Metadata } from "next";

import { JournalBookDemo } from "@/app/journal-demo/journal-book-demo";
import styles from "@/app/journal-demo/journal-demo.module.css";

export const metadata: Metadata = {
  title: "Journal page-turn trial | Travel Journal",
  description:
    "An isolated Mantine Book trial using one repeated static page background.",
};

export default function JournalDemoPage() {
  return (
    <main className={styles.demoShell}>
      <h1 className={styles.visuallyHidden}>Page-turning journal</h1>
      <JournalBookDemo />
    </main>
  );
}
