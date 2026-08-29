# Quality strategy

Status: Repository checks, backend itinerary/preference/provider/worker/media coverage, and frontend lint/type/build verification are **Current**. Automated browser and deployment integration coverage remain **Proposed**.

## Canonical checks

```bash
make check
make smoke
```

`make check` is offline/non-billable and runs:

- Ruff lint/format, pytest, and Alembic offline upgrade SQL.
- Frontend lint, TypeScript check, and production build.
- Resolved Compose configuration validation.

`make smoke` builds/waits for the topology and verifies:

- API live/ready, frontend and same-origin health proxy.
- pgAdmin, Postgres, Redis, worker heartbeat/Postgres health.
- `alembic check`.
- Real itinerary creation and persistence. The legacy terminal-generation smoke is replaced by preference lifecycle coverage because creation no longer starts a run.
- A done result's app-owned media URL, place count, and place links.

Composed smoke creates an itinerary, answers the three initial catalog pairs, completes learning, and polls the worker. With empty generation keys it reaches the safe provider-configuration failure without a provider call; configured keys can consume quota/money.

## Current backend coverage

- City/tag NFKC/whitespace cleaning, length/control/letter constraints, tag deduplication, and extra-field rejection.
- Optional idempotency hashing, semantic city/tag fingerprint, replay current status/header, conflict, and no duplicate learning session.
- Three initial pairs/six activity contracts, four-category catalog coverage, deterministic ranking, optional OpenAI rerank/fallback, single/pair adaptive layouts, activity validation, and unanswered-page replay.
- Itinerary/item-scoped like/dislike upserts, initial-plus-adaptive completion gate, algorithm update hook, single version-4 run creation, and worker notification.
- Worker preference snapshots partition selected/rejected activities in stable page/item order.
- Public projection matrix for all internal statuses, including nullable stage/result/error invariants and incomplete-ready fallback.
- Fixed creation-date-plus-seven-days behavior across retries and valid IANA timezone resolution.
- Cala query/search DTOs, auth, timeouts/errors, empty research, exact URL/entity verification, and context bound.
- OpenAI intent/plan Structured Outputs, invalid/refusal/incomplete/error mapping, schedule/order constraints, and prompt/schema versions.
- Plan checkpoint first-write/immutability, fenced lease loss, and resume without repeated Cala/OpenAI calls.
- fal submit/request-ID checkpoint/resume, timeout/request-ID recovery, invalid/unsafe/multiple-image results, and classified failures.
- Media-copy malformed/local/private URL rejection, DNS/redirect-hop screening, image magic-byte/MIME validation, size/time bounds, atomic write, safe filesystem errors, app URL, and retry classification.
- Completion invariant: three to five places, links/map requirement, exactly one ready hero, and atomic fenced persistence.
- Missing-provider configuration path and no provider calls.
- Redis operation bounds, persist-before-notify, outage/reconciliation, attempt backoff/exhaustion, and worker health.
- All Alembic upgrade paths, schema/model alignment, and revision-0001-through-0004 migration behavior.

The backend suite uses provider/repository/media/algorithm fakes by default. Add targeted multi-worker Postgres integration coverage for learning-page concurrency, row locking, stale-fence races, and migration constraints as risk grows.

## Remaining automated frontend coverage

- City/tag field validation and input preservation.
- Single/pair preference page rendering, item-ID response writes, reload replay, and six-answer completion.
- Polling that honors `Retry-After`, does not resubmit after GET interruption, and stops on terminal status.
- `learning_preferences`, `queued`, `researching`, `planning`, and `illustrating` announcements.
- Complete `done` rendering from result schema and app media URL.
- `fail`, `PROVIDER_CONFIGURATION_MISSING`, validation, and network interruption states.
- Ordered place/link semantics, responsive 4:3 image, alt text, keyboard/focus, contrast, and reduced motion.
- Fixtures generated from or checked against OpenAPI.

## Contract and migration discipline

- FastAPI OpenAPI is canonical for implemented HTTP shapes.
- Public changes update frontend types/fixtures and [API contract](../architecture/api-contract.md) together.
- Persistent changes require a reviewed migration, upgrade/downgrade consideration, and [Domain model](../architecture/domain-model.md) update.
- `alembic check` remains clean.
- Prompt/schema/checkpoint changes require version updates and backward-resume handling.
- Provider-native fields never enter the public API without an explicit domain/ADR decision.
- Live tests remain opt-in because they use network, secrets, quota, nondeterministic providers, and money.

## Definition of done

- `make check` passes; `make smoke` passes for runtime changes in the intended empty-key/configured-key mode.
- Failure, retry, checkpoint, and concurrency risks have proportional tests.
- New settings appear in `.env.example`, Compose where needed, and [Configuration](configuration.md).
- HTTP/schema/boundary changes update documentation and ADRs.
- No secrets, raw provider bodies, generated media, local databases, caches, or unrelated files are committed.
- Current/Proposed labels match verified implementation.
