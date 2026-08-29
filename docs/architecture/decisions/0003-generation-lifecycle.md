# 0003: Postgres-authoritative asynchronous generation

> Creation timing is amended by [ADR 0006](0006-preference-learning-before-generation.md): initial itinerary creation now stores a learning session, and preference completion creates the orchestration run.

- Status: Accepted
- Date: 2026-08-29

## Context

Intent parsing, place research, structured planning, image generation, and media copy exceed an interactive request window. Accepted work must survive API/worker/Redis restarts, lost notifications, provider timeouts, and worker lease loss. Retries must not redo committed expensive side effects, and stale workers must not publish outcomes.

## Decision

Represent generation as a durable asynchronous itinerary resource and make Postgres authoritative for both job state and resume checkpoints.

### API and idempotency

- The accepted-work transaction commits the queued itinerary and orchestration run together before Redis notification. Under ADR 0006 this transaction occurs at preference completion, not initial itinerary creation.
- `GET /api/v1/itineraries/{id}` projects canonical state as `pending`, `done`, or `fail` under [ADR 0004](0004-natural-request-and-journal-artifact.md) and [ADR 0005](0005-city-and-tags-input.md).
- `Idempotency-Key` is optional. Only its SHA-256 hash is stored; a versioned request fingerprint rejects reuse for different cleaned input.

### Notification and recovery

- After commit, the API best-effort appends only the generation-run UUID to a Redis list.
- Redis contains no canonical request, lifecycle, result, lease, checkpoint, prompt, or provider response.
- Enqueue failure does not fail the accepted request.
- Independently of queue traffic, the worker periodically claims any due Postgres row, recovering missed notifications and Redis outages.

### Worker ownership

- A custom asyncio worker runs as its own process. Current Compose has one sequential worker (concurrency `1`).
- Claims use database time and `FOR UPDATE SKIP LOCKED`.
- Claim increments `attempt_count` and `lease_version`, records owner/heartbeat, and sets expiry.
- Lease extension, checkpoint, retry, failure, and completion writes match run ID, running state, owner, fence version, and unexpired lease.
- Retryable failures use bounded attempts and delayed `available_at`; exhaustion becomes terminal.

### Durable checkpoints

- The versioned application-owned plan is saved once in `checkpoint_data` after intent/research/planning validation.
- fal provider/model/request ID is saved once immediately after submission returns.
- Both writes are lease/fence protected and immutable. A retry reuses existing values rather than replanning or resubmitting.
- fal submission and the Postgres request-ID write cannot be atomic. A crash after provider acceptance but before checkpoint commit may cause one duplicate billable submission on retry. Once the checkpoint exists, retrieval is resumable.

### Completion

- Provider output is copied into app-owned media storage before success.
- One fenced transaction persists resolved trip metadata, places/links/evidence, exactly one ready hero, and run/resource completion.
- Any required failure produces terminal `fail`; no incomplete plan is published as success.

### Runtime and readiness

- Compose has six long-running services plus a one-shot migration and shared generated-media volume.
- Postgres is required for API readiness.
- Redis is optional/degraded because durable work remains reconciliable.
- Worker health requires its hostname-scoped Redis heartbeat and a Postgres probe.
- Provider configuration is not a readiness requirement; missing keys fail submitted jobs safely.

## Consequences

- API requests return promptly and accepted work survives process/Redis restarts.
- Redis loss may increase pickup latency but cannot erase work.
- Committed plan/fal checkpoints prevent repeated upstream calls on ordinary retry.
- The fal submit/checkpoint gap remains observable residual duplicate-cost risk.
- Postgres bears reconciliation, locking, checkpoint, lease, and lifecycle load.
- Every worker mutation must use the fenced repository.
- Polling, cancellation, production worker sizing, cleanup, and cost accounting remain separate product/operations decisions.

## Alternatives considered

### Synchronous generation request

Rejected because multiple remote calls create timeout/recovery problems and cannot provide durable polling.

### Redis as authoritative queue/job storage

Rejected because Redis is disposable and cannot be the only copy of accepted work, checkpoints, or terminal state.

### Process only Redis UUIDs

Rejected because notification failure/outage would strand durable runs.

### Transactional outbox for Redis

Deferred. The durable run is directly claimable and reconciliation repairs missed notification. Reconsider if database scan load or wake-up latency becomes unacceptable.

### Re-run the entire pipeline on every attempt

Rejected because it changes the plan, repeats cost, and can create multiple fal submissions even after their IDs are known.
