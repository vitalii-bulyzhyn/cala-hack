# Delivery plan

Status: Milestones 0–7 are **Current product capability**. Milestone 8 remains **Proposed** for reliability and demo hardening.

## Milestone 0 — Development foundation

Status: **Complete**.

- Monorepo, Next.js/FastAPI apps, Postgres, Redis, pgAdmin, worker, migration service, Compose, Make targets, health/provider status, and backend-only secrets.
- `make dev`, `make setup`, `make check`, and `make smoke` provide canonical workflows.

Exit: the six-service stack plus one-shot migration boots, and offline checks require no provider key.

## Milestone 1 — City/tag contract and migrations

Status: **Complete**.

- `POST {"city": ..., "tags": [...]}` validates both fields with optional hashed idempotency.
- `GET` exposes `pending|done|fail`, nullable stage/result/error, and the complete result schema.
- Revision `20260829_0002` adds request text, destination/date/timezone, place links, checkpoints, and the unique hero constraint.
- Revision `20260829_0003` replaces request text with separately stored city and JSONB tags.

Exit: OpenAPI and Postgres enforce the contract; migrations upgrade a revision-0001 or revision-0002 database.

## Milestone 2 — Preference-learning contract

Status: **Complete**.

- Creation stores a collecting learning session and does not start generation.
- Persist three initial pair pages/six items from the algorithm, followed by optional single/pair adaptive pages.
- Upsert `like|dislike` decisions against exact itinerary/item IDs.
- Require the six initial responses plus an answered adaptive page before creating the one generation run.
- Pass selected/rejected activity snapshots to worker planning.
- Rank an extendable four-category catalog deterministically; optionally use OpenAI for adaptive reranking with local fallback.

Exit: HTTP and Postgres contracts are stable, page/response/completion behavior is tested, and the injected algorithm can be implemented without persistence/API changes.

## Milestone 3 — Trip intent and Cala research

Status: **Complete**.

- Resolve canonical destination and IANA timezone from city input; use stored tags plus selected/rejected activity snapshots as preferences.
- Set the planned date to immutable UTC creation date plus seven days.
- Run Cala knowledge query and search, validate their DTOs, and retain evidence without live-data claims.

Exit: empty/invalid/unavailable research maps to stable errors and never fabricates a place link.

## Milestone 4 — OpenAI structured planning

Status: **Complete**.

- Use the Responses API and Pydantic Structured Outputs for intent and the final plan.
- Produce three to five consecutive, non-overlapping places using only Cala-grounded data.
- Permit official/source URLs only when present verbatim in research; construct a map-search link per place.
- Version the plan/checkpoint and prompt schemas.

Exit: application validation rejects unsupported URLs, malformed schedules, incomplete plan data, refusals, and invalid output.

## Milestone 5 — Durable orchestration and checkpoints

Status: **Complete**.

- Postgres remains authoritative; Redis carries run-ID wake-ups only.
- Claims, heartbeats, retries, success/failure, and both checkpoints are lease/fence protected.
- Retries reuse the immutable application plan and saved fal request ID.
- Reconciliation finds due work independently of Redis traffic.

Exit: lost notifications and worker restarts preserve accepted work, and stale workers cannot overwrite state.

## Milestone 6 — fal hero and app-owned media

Status: **Complete for local/demo storage**; production storage is **Open**.

- Submit one seeded 4:3 JPEG through fal's asynchronous queue with safety checking.
- Persist provider/model/request ID before waiting when possible, then resume retrieval on retry.
- Validate one image result, copy supported content within size/time limits, and write atomically to shared app storage.
- Require exactly one ready hero for `done`; any core/image/storage failure yields `fail`.

Exit: successful API results use an absolute backend-origin URL backed by stored `/media/...` media, not an expiring fal URL. The unavoidable submit-before-checkpoint crash window is documented and observable.

Unresolved: production object store/CDN, retention, deletion, ACLs, and public URL ownership.

## Milestone 7 — Journal frontend

Status: **Complete for the integrated local product**.

- Build city/tag entry, single/pair visual preference pages, response/completion flow, and `pending`, `done`, `fail` states.
- Honor `Retry-After`; never resubmit merely because polling failed.
- Render destination/date/title/summary, responsive 4:3 hero, and accessible ordered place details/links.
- Preserve all essential content outside the generated image.

Exit: frontend types align with the current OpenAPI shapes, the production build passes, and the durable itinerary ID connects every screen without resubmission.

Unresolved: automated browser-state coverage, final brand/typography, and deployment routing for `/media`.

## Milestone 8 — Reliability and demo hardening

Status: **Proposed**.

- Add deterministic fake-provider end-to-end coverage plus an explicitly billable live-provider check.
- Record provider/stage latency, usage, retry, checkpoint, duplicate-submission suspicion, and safe error telemetry.
- Add rate/cost limits, known-good demo requests, recovery runbook, and storage cleanup policy.
- Choose deployment, production storage/networking, CORS, and secret injection.

Exit: `make check` and `make smoke` pass; a live configured run reaches `done`; expected failures are diagnosable without secrets.

## Cross-cutting rules

- Never mark `done` without one complete result, three to five places, and one app-owned ready hero.
- Provider calls stay backend-only and provider payloads stay behind adapters.
- Tests are offline by default; live calls are explicit because they use credentials, quota, and money.
- Update Current documentation only with implemented, verified behavior.
- Add or supersede an ADR for public-contract, durable-state, media-storage, or deployment-boundary changes.
