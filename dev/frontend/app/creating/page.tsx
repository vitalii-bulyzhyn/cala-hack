import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { GenerationStatus } from "@/app/creating/generation-status";
import styles from "@/app/product-flow.module.css";

export const metadata: Metadata = {
  title: "Creating your travel journal | Travel Journal",
};

type CreatingPageProps = {
  searchParams: Promise<{
    id?: string | string[];
  }>;
};

export default async function CreatingPage({
  searchParams,
}: CreatingPageProps) {
  const params = await searchParams;
  const id = params.id;

  if (typeof id !== "string" || !id) {
    redirect("/");
  }

  return (
    <main className={styles.generationShell}>
      <section aria-busy="true" className={styles.generationPanel}>
        <GenerationStatus itineraryId={id} />
      </section>
    </main>
  );
}
