import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PreferenceLearning } from "@/app/preferences/preference-learning";

export const metadata: Metadata = {
  title: "Choose your kind of day | Travel Journal",
};

export default async function PreferencesPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string | string[] }>;
}) {
  const { id } = await searchParams;
  if (typeof id !== "string" || !id) {
    redirect("/");
  }
  return <PreferenceLearning itineraryId={id} />;
}
