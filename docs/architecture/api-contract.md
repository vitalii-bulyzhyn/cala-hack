# API contract

Status: Operational endpoints, city/tag creation, preference-learning pages/responses, and `pending|done|fail` polling are **Current**. FastAPI OpenAPI at `/docs` is authoritative for executable schemas.

The local backend origin is `http://localhost:8000`; OpenAPI JSON is `/api/v1/openapi.json`.

## Operational and media endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health/live` | Process liveness; calls no dependency. |
| `GET` | `/api/v1/health/ready` | Requires Postgres; reports Redis as optional/degraded. |
| `GET` | `/api/v1/providers/status` | Redacted provider configuration presence; contacts no provider. |
| `GET` | `/media/{storage_key}` | Serves an app-owned generated file. |

Readiness is HTTP `503` only when a required check fails. Postgres has `required: true`; Redis has `required: false`.

## Create an itinerary

```http
POST /api/v1/itineraries
Content-Type: application/json
Idempotency-Key: optional-client-key
```

```json
{
  "city": "Barcelona",
  "tags": ["art", "old streets", "local food", "relaxed pace"]
}
```

Request validation:

- Exactly `city` and `tags`; extra fields are rejected and both fields are required.
- City is canonical `Barcelona`, `Toulouse`, or `Valencia`; other values are rejected because no substitute inventory exists.
- Tags is an array of zero to twenty strings. Each tag uses the same Unicode/control rules and is 1–50 characters.
- Duplicate tags are removed case-insensitively while preserving the first spelling and position.

`Idempotency-Key` is optional and accepts 1–128 ASCII letters, digits, `.`, `_`, `:`, or `-`. The backend stores only its SHA-256 hash and separately fingerprints normalized city plus a case-insensitive, order-independent tag set.

A fresh successful request returns `202 Accepted` after one Postgres transaction commits the itinerary and its preference-learning session. It does not create or enqueue generation work yet:

```json
{
  "id": "52cf6f93-9fbc-4f97-a815-74b8fedcb8b1",
  "status": "pending",
  "status_url": "/api/v1/itineraries/52cf6f93-9fbc-4f97-a815-74b8fedcb8b1"
}
```

The response reports the resource's current public status. A replay may therefore return `pending`, `done`, or `fail`; clients must not assume every `202` contains `pending`.

Response headers:

- `Location` — same relative path as `status_url`.
- No `Retry-After` is sent by initial creation because no worker run exists while learning.
- `Cache-Control: no-store`.
- `Idempotency-Replayed: true` only for an existing compatible resource.
- `X-Request-ID` on every API response.

The new resource has internal stage `learning_preferences`. The frontend uses the returned ID with the preference APIs below. Generation is created and best-effort enqueued only after preference learning is completed.

### Idempotency behavior

- No header: every accepted call creates a new resource.
- Same key and equivalent cleaned city/tags: return the original resource/current status and do not create another learning session.
- Same key and a different city or tag set: `409 IDEMPOTENCY_KEY_REUSED`.
- Whitespace/NFKC-equivalent cities replay. Tag order, case, and duplicates do not change the fingerprint.
- Concurrent duplicates are resolved through the unique stored key hash.

## Preference learning

Preference learning is scoped to one itinerary. Its injected algorithm interface is implemented by `city-journal-bandit-v1`: deterministic ranking over the exact Barcelona, Toulouse, or Valencia journal inventory for the initial six, followed by optional OpenAI reranking with deterministic fallback and durable Thompson Sampling for one adaptive page. Unsupported cities have no substitute inventory. The unconfigured implementation remains available for explicit injection/tests and returns `503 PREFERENCE_ENGINE_NOT_CONFIGURED`.

### List issued pages

```http
GET /api/v1/itineraries/{itinerary_id}/preference-pages
```

Returns a JSON array of every persisted preference page in ascending `position`, using the same page and entry shape documented below. Each entry includes its current nullable `decision`, so the client can restore votes while letting the traveler flip among all issued faces. The response is `[]` before any page has been issued and uses `Cache-Control: no-store`.

This endpoint is strictly read-only: it does not call the preference algorithm, create an initial or adaptive page, require a response on the current page, or change learning/completion state. The client first calls `GET .../preference-pages/next` to issue the three initial pairs, then can use this collection endpoint to render and navigate all six initial activity faces without voting first. If all issued entries are answered, `GET .../next` remains the only operation that can optionally issue an adaptive page or return `204`; clients may instead complete learning directly.

### Get the next page

```http
GET /api/v1/itineraries/{itinerary_id}/preference-pages/next
```

The first call asks the algorithm for exactly three initial pairs, persists all six activities as three pages, and returns page one. Repeated calls return the earliest page with unanswered entries; use the read-only collection endpoint above when the UI needs to browse the other already-issued pages before responding. After every issued entry has a response, the algorithm may return an adaptive page containing either one activity or a pair. `204 No Content` means it has no next page. Responses use `Cache-Control: no-store`.

```json
{
  "id": "d3807497-e058-4cf8-a806-b99ae31bc9ee",
  "position": 1,
  "layout": "pair",
  "source": "initial",
  "entries": [
    {
      "id": "0664f4fd-a1bf-4d06-8629-f93062d900a1",
      "name": "Basílica de la Sagrada Família",
      "category": "culture",
      "description": "I spent a quiet part of the morning inside the Basílica de la Sagrada Família...",
      "image_link": null,
      "decision": null
    },
    {
      "id": "fe11b9d1-f562-41d2-92f9-d1c005b98877",
      "name": "Pa amb tomàquet",
      "category": "food",
      "description": "In Gràcia, I asked for pa amb tomàquet at Taverna El Glop...",
      "image_link": null,
      "decision": null
    }
  ]
}
```

`layout` is `single` for one entry or `pair` for two. `source` is `initial` for the first six choices and `adaptive` afterward. Every entry has an ID, name, category, journal description, nullable HTTP(S) image link, and nullable recorded `decision`, so a partial-page reload restores what the user already chose. Current authoritative entries have `image_link: null`; private Cala metadata is not exposed.

### Replace page feedback atomically

```http
PUT /api/v1/itineraries/{itinerary_id}/preference-pages/{page_id}/feedback
Content-Type: application/json
```

```json
{
  "decisions": {
    "0664f4fd-a1bf-4d06-8629-f93062d900a1": "like",
    "fe11b9d1-f562-41d2-92f9-d1c005b98877": null
  }
}
```

Each supplied decision is `like`, `dislike`, or `null`; omitted and null items are neutral. The page must belong to the itinerary and every supplied item must belong to the page. In one transaction the API locks the collecting session/page, upserts explicit responses, deletes responses changed to neutral, rebuilds the bandit state from all durable responses, and commits the page. Equivalent replay is idempotent. The response is the updated page shape shown above.

### Complete learning and start generation

```http
POST /api/v1/itineraries/{itinerary_id}/preference-learning/complete
```

Completion is allowed at any time while the learning session is collecting, including when some or every issued entry is unanswered and when no adaptive page exists. Under the same learning-session lock used by feedback, the API reloads final responses, rebuilds/finalizes state, atomically closes learning, transitions the itinerary to `queued`, and creates one version-4 orchestration run. It then best-effort notifies Redis. Replays return the same resource and do not create a second run; after completion, feedback and page issuance remain closed.

The `202` body matches itinerary creation: `id`, `status: "pending"`, and `status_url`. It includes `Retry-After` for worker polling. The worker receives original city/tags plus the full selected/rejected activity snapshots. Only after this endpoint should the frontend poll for generated output.

## Get an itinerary

```http
GET /api/v1/itineraries/{itinerary_id}
```

Every success is `200 OK`, `Cache-Control: no-store`, and the same stable envelope:

```json
{
  "id": "52cf6f93-9fbc-4f97-a815-74b8fedcb8b1",
  "city": "Barcelona",
  "tags": ["art", "old streets", "local food", "relaxed pace"],
  "status": "pending",
  "stage": "learning_preferences",
  "result": null,
  "error": null,
  "created_at": "2026-08-29T12:00:00Z",
  "updated_at": "2026-08-29T12:00:01Z",
  "completed_at": null
}
```

`Retry-After` is present only for a pending generation-stage GET (`queued`, `researching`, `planning`, or `illustrating`), not during `learning_preferences`.

### Public status invariants

| Status | `stage` | `result` | `error` | `completed_at` |
| --- | --- | --- | --- | --- |
| `pending` | `learning_preferences`, `queued`, `researching`, `planning`, or `illustrating` | `null` | `null` | `null` |
| `done` | `null` | complete object | `null` | timestamp |
| `fail` | `null` | `null` | safe error object | timestamp |

There is no public partial state. An internally ready row that cannot produce every required result field is projected as `fail` with `RESULT_INCOMPLETE`.

### Done response

```json
{
  "id": "52cf6f93-9fbc-4f97-a815-74b8fedcb8b1",
  "city": "Barcelona",
  "tags": ["art", "old streets", "local food", "relaxed pace"],
  "status": "done",
  "stage": null,
  "result": {
    "destination": "Barcelona, Spain",
    "planned_date": "2026-09-05",
    "destination_timezone": "Europe/Madrid",
    "title": "Barcelona in Ink and Sunlight",
    "summary": "A relaxed day of art, historic streets, and Catalan food.",
    "journal_image": {
      "id": "30a9ac2e-8ae0-4c50-aec8-d3f0236ac4ac",
      "url": "http://localhost:8000/media/52cf6f93-9fbc-4f97-a815-74b8fedcb8b1/journal.jpg",
      "content_type": "image/jpeg",
      "width": 1600,
      "height": 1200,
      "alt_text": "Hand-drawn one-day travel journal for Barcelona, featuring three planned places."
    },
    "places": [
      {
        "id": "bc24313d-bdbb-4777-9fe7-927e86ceee1d",
        "position": 1,
        "start_time": "09:30",
        "end_time": "11:00",
        "name": "Museu Picasso de Barcelona",
        "category": "museum",
        "description": "Begin among Picasso's formative works in medieval palaces.",
        "reason_to_visit": "It joins the art focus with the texture of the old city.",
        "location": {
          "address": "Carrer de Montcada, Barcelona",
          "latitude": 41.3852,
          "longitude": 2.1809
        },
        "links": [
          {
            "kind": "map",
            "label": "Open in maps",
            "url": "https://www.google.com/maps/search/?api=1&query=..."
          },
          {
            "kind": "official",
            "label": "Official website",
            "url": "https://..."
          }
        ]
      }
    ]
  },
  "error": null,
  "created_at": "2026-08-29T12:00:00Z",
  "updated_at": "2026-08-29T12:01:20Z",
  "completed_at": "2026-08-29T12:01:20Z"
}
```

The example is abbreviated to one place; actual generated results contain three to five in ascending `position`. Time strings are local `HH:MM` in `destination_timezone`.

`location` is either `null` or an object with nullable address/coordinates; latitude and longitude are either both present or both absent. Link kinds are:

- `map` — application-created map search; required for every place and not evidence of live route data.
- `official` — exact URL copied from Cala research.
- `source` — exact supporting URL copied from Cala research.

The public `journal_image.url` is an absolute URL on the backend origin and points to the copied app-owned file, never directly to fal. Postgres stores the corresponding relative `/media/...` URL; the API resolves it against the request base URL when projecting the result.

### Date resolution

The worker uses the resource's immutable UTC creation date on every attempt:

- the current create contract has no date field;
- planned date is always reference date plus seven days;
- the resolved IANA timezone is returned separately from the date/local place times.

### Fail response

For example, incomplete provider configuration produces this response when `OFFLINE_DEMO_ENABLED=false`:

```json
{
  "id": "52cf6f93-9fbc-4f97-a815-74b8fedcb8b1",
  "city": "Barcelona",
  "tags": ["art", "local food"],
  "status": "fail",
  "stage": null,
  "result": null,
  "error": {
    "code": "PROVIDER_CONFIGURATION_MISSING",
    "message": "Itinerary generation is not configured. Missing: OPENAI_API_KEY, CALA_API_KEY, FAL_KEY.",
    "retryable": false,
    "request_id": "job_..."
  },
  "created_at": "2026-08-29T12:00:00Z",
  "updated_at": "2026-08-29T12:00:01Z",
  "completed_at": "2026-08-29T12:00:01Z"
}
```

Async provider/validation failures are represented on the durable resource with HTTP `200`; they are not transport errors. Stable code families include city/destination/date validation, Cala research, OpenAI output, fal submission/result/safety, media download/storage, checkpoint/output validation, and attempt exhaustion.

## Immediate error envelope

Request/persistence failures use:

```json
{
  "error": {
    "code": "ITINERARY_NOT_FOUND",
    "message": "The requested itinerary does not exist.",
    "retryable": false,
    "request_id": "req_..."
  }
}
```

| HTTP | Code | Meaning |
| --- | --- | --- |
| `404` | `ITINERARY_NOT_FOUND` | UUID does not identify a resource. |
| `404` | `PREFERENCE_ITEM_NOT_FOUND` | Item does not belong to the itinerary. |
| `409` | `IDEMPOTENCY_KEY_REUSED` | Key belongs to different city/tag input. |
| `409` | `PREFERENCE_LEARNING_CLOSED` | Learning has already completed. |
| `503` | `PREFERENCE_ENGINE_NOT_CONFIGURED` | An explicitly injected algorithm implementation is unavailable. |
| `502` | `PREFERENCE_ENGINE_INVALID_OUTPUT` | Algorithm output violated the activity/page contract. |
| `503` | `SERVICE_UNAVAILABLE` | Required Postgres create/read failed; retryable. |
| `500` | `INTERNAL_ERROR` | Unexpected API error was sanitized; retryable. |

FastAPI returns standard `422` for invalid bodies, headers, or UUID path values. Raw prompts, provider responses, evidence, idempotency hashes, leases/checkpoints, secrets, and stack traces are never returned.

## Contract rules

- Application routes are fixed under `/api/v1`; changing the prefix is a public-contract change.
- Public IDs are UUIDs; timestamps are ISO 8601 and dates are `YYYY-MM-DD`.
- Polling is safe and non-cacheable. Clients honor `Retry-After` and never create a new resource solely because GET failed.
- A done result is atomic and complete; no provider-specific type appears in the schema.
- Frontend types/fixtures must be generated from or checked against OpenAPI.

Persistence/checkpoint details are in [Domain model](domain-model.md); rationale is in [ADR 0004](decisions/0004-natural-request-and-journal-artifact.md), [ADR 0005](decisions/0005-city-and-tags-input.md), and [ADR 0006](decisions/0006-preference-learning-before-generation.md).
