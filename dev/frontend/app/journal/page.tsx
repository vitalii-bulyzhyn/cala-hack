import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { JournalResult } from "@/app/journal/journal-result";

export const metadata: Metadata = {
  title: "Your journal | Travel Journal",
};

type JournalPageProps = {
  searchParams: Promise<{
    id?: string | string[];
  }>;
};

export default async function JournalPage({ searchParams }: JournalPageProps) {
  const params = await searchParams;
  if (typeof params.id !== "string" || !params.id) {
    redirect("/");
  }
  return <JournalResult itineraryId={params.id} />;
}
