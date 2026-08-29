# Travel Journal API

Python 3.12/FastAPI backend for durable preference learning and one-day itinerary generation. City/tags, visual activity pages, and like/dislike responses are persisted before Cala/OpenAI/fal worker generation starts.

## Run locally

From the repository root, run `make dev` for the complete Docker stack. For host-local processes:

```bash
make infra-up
make setup
make migrate
make backend-dev
```

Run `make worker-dev` separately. Configuration comes from the process environment and monorepo-root `.env`; process values win. Provider credentials are not required to boot, but a generation job cannot succeed without all three.

## Endpoints

- `GET /api/v1/health/live` — process liveness; calls no dependency.
- `GET /api/v1/health/ready` — requires Postgres and reports Redis as optional/degraded.
- `GET /api/v1/providers/status` — redacted configuration presence; no provider call.
- `POST /api/v1/itineraries` — accepts `{"city":"Barcelona","tags":["art","local food"]}` and returns `202` plus the resource's current public status.
- `GET /api/v1/itineraries/{itinerary_id}` — returns `pending`, `done`, or `fail`, a stable pending stage or `null`, and mutually exclusive result/error data.
- `GET /api/v1/itineraries/{itinerary_id}/preference-pages` — lists every issued page and its current decisions without advancing learning.
- `GET /api/v1/itineraries/{itinerary_id}/preference-pages/next` — returns/replays the current single/pair page, creates the next algorithm page when required, or returns `204`.
- `PUT /api/v1/itineraries/{itinerary_id}/preference-items/{item_id}/response` — upserts `{"decision":"like|dislike"}` for the exact issued item.
- `POST /api/v1/itineraries/{itinerary_id}/preference-learning/complete` — closes learning with zero or more recorded responses and creates/enqueues generation.
- `GET /api/v1/openapi.json` — OpenAPI schema.
- `GET /docs` — Swagger UI.
- `GET /media/{storage_key}` — app-owned generated image bytes.

The city is NFKC-normalized, whitespace-collapsed, limited to 1–160 characters, must contain a letter, and rejects control characters. `tags` is required, may be empty, contains at most 20 labels of 1–50 characters, and is cleaned and case-insensitively deduplicated while preserving first occurrence order. Extra fields are rejected.

An optional `Idempotency-Key` accepts 1–128 letters, digits, `.`, `_`, `:`, or `-`. Only its SHA-256 hash is stored. The same key and equivalent cleaned city/tag input replay the resource without creating another learning session; different input returns `409 IDEMPOTENCY_KEY_REUSED`.

## Preference-learning seam

Creation atomically stores the itinerary and a collecting learning session in stage `learning_preferences`; it deliberately creates no generation run. `PreferenceLearningAlgorithm` defines `get_initial_pairs`, `get_next_page`, and `update_learning_algorithm`. The default `catalog-bandit-v1` implementation ranks a curated four-category catalog deterministically and may use OpenAI for adaptive reranking when configured; its fallback requires no key.

The implemented persistence contract requires three initial pairs (six entries), allows later single/pair pages, and stores every entry's UUID, name, category, description, and HTTP(S) image link. Responses are itinerary/item-scoped upserts and become immutable at completion. Completion is allowed with unanswered items, creates deduplicated orchestration version 4, and passes only recorded likes/dislikes in the selected/rejected snapshots to the worker.

The full public representation, headers, examples, and invariants are in [`docs/architecture/api-contract.md`](../../docs/architecture/api-contract.md).

## Durable worker and checkpoints

Preference completion commits the closed learning session, queued itinerary, and orchestration run before best-effort Redis notification. Creation itself has no work to notify. The worker also scans due Postgres work independently of queue traffic.

The pipeline:

1. Resolves the canonical destination and IANA timezone from the city, uses stored tags plus selected/rejected activity snapshots, and assigns a date exactly seven days after creation.
2. Runs Cala knowledge query and search, then creates a validated OpenAI Responses plan with three to five places.
3. Saves that application-owned plan as an immutable fenced checkpoint.
4. Submits one 4:3 hero image to fal and saves provider/model/request ID as a second fenced checkpoint.
5. On retry, resumes the saved plan and fal request rather than repeating completed side effects.
6. Copies the provider image into app-owned storage and atomically records the complete result.

There is an unavoidable crash window after fal accepts a submission but before its request ID commits to Postgres. A retry can submit a duplicate billable request in that narrow window. Once the ID checkpoint commits, retries only retrieve that request.

All core planning and image steps are required. Any exhausted/non-retryable failure produces public `fail`; there is no public partial success. By default, incomplete provider credentials select the deterministic, network-free demo pipeline. Set `OFFLINE_DEMO_ENABLED=false` to require all providers and use `PROVIDER_CONFIGURATION_MISSING` for incomplete configuration.

## Dates and result data

The planned day defaults to seven days after `itineraries.created_at` converted to its immutable UTC date. The result exposes that date and the resolved destination IANA timezone. Place times are local `HH:MM` values.

Every place has an app-created map search link. `official` and `source` links are included only when their exact URL appeared in Cala research; OpenAI may not invent them.

## Provider and media boundaries

- Cala calls `/v1/knowledge/query` and `/v1/knowledge/search` with `X-API-KEY`.
- OpenAI uses the Responses API with application-owned Pydantic structured-output schemas.
- fal uses asynchronous queue submission/retrieval and produces exactly one candidate image.
- The worker downloads supported image content with size/time limits, writes it atomically, and stores an app-owned relative `/media/...` URL. The API returns that media URL as an absolute URL on its request origin.

Compose mounts the same `generated_media` volume into API and worker. Host-local storage defaults to `.data/generated-media`. Local storage is not the production storage decision.

## Database migrations

- `20260829_0001` creates itineraries, stops, media assets, and generation runs.
- `20260829_0002` migrates to natural-language requests, resolved destination/date/timezone, typed place-link JSON, plan checkpoint data, and one itinerary-level hero constraint.
- `20260829_0003` replaces request text with separately stored `city` and JSONB `tags` fields.
- `20260829_0004` adds the learning stage and durable sessions, pages, items, and responses; existing itineraries are backfilled as completed.

API and worker never create or upgrade schema. Compose runs `alembic upgrade head` in a one-shot `migrate` service.

```bash
make migrate
cd dev/backend
.venv/bin/alembic current
.venv/bin/alembic revision --autogenerate -m 'describe the change'
```

## Quality checks

```bash
make check
make smoke
```

Offline tests use fakes and must not require credentials or billable calls. `make smoke` uses the credentials present in `.env`: empty keys exercise a terminal configuration failure, while real keys exercise and may bill the live pipeline.
