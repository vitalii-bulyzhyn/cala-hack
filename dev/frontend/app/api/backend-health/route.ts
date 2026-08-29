import { NextResponse } from "next/server";

import { checkBackendHealth } from "@/lib/backend";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const health = await checkBackendHealth();

  return NextResponse.json(health, {
    status: health.connected ? 200 : 503,
    headers: {
      "Cache-Control": "no-store, max-age=0",
    },
  });
}
