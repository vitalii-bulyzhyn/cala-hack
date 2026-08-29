import type {
  ApiError,
  ItineraryAccepted,
  ItineraryResource,
  PreferencePage,
} from "@/lib/api-contract";

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function apiUrl(path: string) {
  const baseUrl = (
    process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL
  ).replace(/\/+$/, "");
  return `${baseUrl}${path}`;
}

export class TravelJournalApiError extends Error {
  code: string;
  retryable: boolean;
  requestId?: string;

  constructor(message: string, code = "NETWORK_ERROR", retryable = true, requestId?: string) {
    super(message);
    this.name = "TravelJournalApiError";
    this.code = code;
    this.retryable = retryable;
    this.requestId = requestId;
  }
}

async function responseError(response: Response) {
  try {
    const payload = (await response.json()) as ApiError;
    return new TravelJournalApiError(
      payload.error.message,
      payload.error.code,
      payload.error.retryable,
      payload.error.request_id,
    );
  } catch {
    return new TravelJournalApiError(
      "The travel journal service could not complete that request.",
      `HTTP_${response.status}`,
      response.status >= 500,
    );
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new TravelJournalApiError(
      "We could not reach the travel journal service. Check the backend and try again.",
    );
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as T;
}

export function createItinerary(city: string, tags: string[], idempotencyKey: string) {
  return request<ItineraryAccepted>("/api/v1/itineraries", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ city, tags }),
  });
}

export async function getNextPreferencePage(itineraryId: string) {
  let response: Response;
  try {
    response = await fetch(
      apiUrl(`/api/v1/itineraries/${itineraryId}/preference-pages/next`),
      { cache: "no-store", headers: { Accept: "application/json" } },
    );
  } catch {
    throw new TravelJournalApiError(
      "We could not load the next activity choice. Try again without starting over.",
    );
  }
  if (response.status === 204) {
    return null;
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as PreferencePage;
}

export function getPreferencePages(itineraryId: string) {
  return request<PreferencePage[]>(
    `/api/v1/itineraries/${itineraryId}/preference-pages`,
  );
}

export function recordPreference(
  itineraryId: string,
  itemId: string,
  decision: "like" | "dislike",
) {
  return request<unknown>(
    `/api/v1/itineraries/${itineraryId}/preference-items/${itemId}/response`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
}

export function completePreferenceLearning(itineraryId: string) {
  return request<ItineraryAccepted>(
    `/api/v1/itineraries/${itineraryId}/preference-learning/complete`,
    { method: "POST" },
  );
}

export async function getItineraryStatus(itineraryId: string) {
  let response: Response;
  try {
    response = await fetch(apiUrl(`/api/v1/itineraries/${itineraryId}`), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new TravelJournalApiError(
      "We could not reach the travel journal service. Check the backend and try again.",
    );
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  const retryAfterSeconds = Number(response.headers.get("Retry-After"));
  return {
    resource: (await response.json()) as ItineraryResource,
    retryAfterMs:
      Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
        ? retryAfterSeconds * 1_000
        : 2_000,
  };
}

export async function getItinerary(itineraryId: string) {
  return (await getItineraryStatus(itineraryId)).resource;
}
