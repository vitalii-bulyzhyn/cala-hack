# Domain model

Status: Revisions `20260829_0001` through `20260829_0004`, preference learning, the public projection, provider lifecycle, checkpoints, and local media ownership are **Current**.

## Ownership

Postgres is the source of truth for accepted requests, internal lifecycle, checkpoints, and results. Redis contains only reconstructible run UUIDs and a hostname-scoped worker heartbeat. App-owned media contains image bytes; Postgres stores its metadata/key. Provider DTOs never define the public model.

## Current entities

### Itinerary

One durable city/tag resource that learns preferences before generation.

| Field group | Contents |
| --- | --- |
| Identity/input | UUID `id`, 1–160-character `city`, JSONB `tags`, versioned request fingerprint |
| Idempotency | optional unique SHA-256 key hash; raw key is never stored |
| Resolved trip | nullable-until-success `destination`, `planned_date`, and IANA `destination_timezone` |
| Plan/result | internal `status`, nullable `title` and `summary` |
| Error | safe code/message/retryable flag/job request ID |
| Concurrency/audit | nonnegative state version, status-change/completion/create/update timestamps |

`created_at` converted to its UTC date is the immutable `reference_date`; the planned day is that date plus seven days on every attempt.

### PreferenceLearningSession

One itinerary-owned session with `collecting|completed` status, algorithm version, completion timestamp, and audit timestamps. Creation inserts it with the itinerary. Existing pre-revision-0004 resources are backfilled as `completed` with `legacy-preference-bypass`.

### PreferencePage and PreferenceItem

An ordered page belongs to the itinerary session and records:

- stable UUID and consecutive positive page position;
- `single|pair` layout and `initial|adaptive` source;
- exactly one or two ordered items at the application layer.

Every item stores an immutable UUID, itinerary/page association, position, name, category, description, and HTTP(S) `image_link`. The initial algorithm result must be exactly three pair pages, six items total.

### PreferenceResponse

One unique response per `(itinerary_id,item_id)` with `like|dislike` decision and timestamps. Composite foreign keys prevent cross-itinerary responses. The API upserts a response while the session is collecting; completion makes all preference state immutable.

### Stop

An ordered planned place belonging to an itinerary.

| Field group | Contents |
| --- | --- |
| Identity/order | UUID, itinerary UUID, consecutive position `1..10` (real pipeline emits `3..5`) |
| Local schedule | `start_time`, `end_time`; start precedes end and places do not overlap |
| Copy | name, category, description, reason to visit |
| Location | optional address; latitude/longitude must be paired and bounded |
| Grounding | optional Cala entity ID, JSON evidence, retrieval time/confidence |
| Public links | JSON list of `{kind,label,url}` with kinds `map`, `official`, or `source` |

Every successful place has a `map` link built by the application. An `official` or `source` URL is admitted only if the exact URL occurs in Cala research. Links are validated as public HTTP(S) URLs and provider-specific payloads remain private.

### MediaAsset

Generated-media metadata associated with the itinerary or a stop.

| Field group | Contents |
| --- | --- |
| Identity/link | UUID, itinerary UUID, optional stop UUID |
| Lifecycle | role, status, provider/request ID, nonnegative attempt count |
| App output | stored relative `/media/...` URL, application storage key, content type, dimensions |
| Provider/presentation | optional provider expiry, alt text, model ID, prompt version |
| Failure/audit | safe error code/message and timestamps |

The real pipeline creates exactly one itinerary-level `hero`; a partial unique index prevents a second hero. `stop_illustration` remains in the foundational schema but is not part of the current product flow. Success requires one ready hero with URL, storage key, supported image type, positive dimensions, and alt text. The public projection resolves the stored relative URL against the backend request origin.

### GenerationRun

Durable private work state for orchestration/provider stages.

| Field group | Contents |
| --- | --- |
| Identity/link | UUID, itinerary UUID, optional media UUID, unique dedupe key |
| Work | stage/status, attempts/max, queue/availability/start/finish times |
| Lease/fencing | owner, nonnegative version, expiry, heartbeat |
| Checkpoints | application plan JSON; fal provider/model/request ID |
| Diagnostics | prompt/schema/model IDs, usage JSON, safe retryable error metadata |

Preference completion uses dedupe key `itinerary:{itinerary_id}:orchestration:v4`. Creation itself creates no generation run.

## Internal enums

Internal itinerary status:

```text
learning_preferences | queued | researching | planning | illustrating | ready | partial | failed
```

The real pipeline never completes `partial`; the value remains for foundational schema compatibility and projects publicly to `fail`.

Generation stage:

```text
orchestration | research | planning | illustration
```

Generation-run status:

```text
queued | running | retry_wait | succeeded | failed
```

Media status and role:

```text
pending | queued | generating | ready | failed
hero | stop_illustration
```

## Public projection

| Internal itinerary state | Public status | Public stage | Result | Error |
| --- | --- | --- | --- | --- |
| `learning_preferences` | `pending` | `learning_preferences` | `null` | `null` |
| `queued` | `pending` | `queued` | `null` | `null` |
| `researching` | `pending` | `researching` | `null` | `null` |
| `planning` | `pending` | `planning` | `null` | `null` |
| `illustrating` | `pending` | `illustrating` | `null` | `null` |
| `ready` with complete projection | `done` | `null` | complete object | `null` |
| `failed` or legacy `partial` | `fail` | `null` | `null` | safe error |
| `ready` with incomplete projection | `fail` | `null` | `null` | synthesized `RESULT_INCOMPLETE` |

There is no public partial state.

## Date and plan invariants

- City is NFKC-normalized, whitespace-collapsed, contains a letter, contains no control character, and is at most 160 characters.
- Tags is required as an array, may be empty, has at most 20 entries, and each entry follows the same text rules with a 50-character limit.
- Tags are case-insensitively deduplicated for storage, while idempotency additionally treats tag order as irrelevant.
- Creation commits the itinerary and learning session atomically, with no generation run.
- Initial suggestions are exactly three pairs; later suggestions contain one item or one pair.
- Completion may close a collecting session with zero, partial, or complete responses and without an adaptive page; unanswered items are neutral and omitted from selected/rejected snapshots.
- Completion atomically closes learning, changes `learning_preferences -> queued`, and creates exactly one version-4 run.
- Planned date is the immutable UTC reference date plus seven days.
- Destination timezone is a valid IANA name.
- The provider plan contains three to five places, positions consecutive from one, and non-overlapping local time windows.
- Unsupported addresses, coordinates, entity IDs, and verified URLs are null/omitted rather than invented.

## Checkpoint and fencing rules

- Claims use database time and `FOR UPDATE SKIP LOCKED`, increment attempt/fence version, and set owner/heartbeat/expiry.
- Extend, checkpoint, retry, failure, and success writes match run ID, running state, owner, fence version, and unexpired lease.
- `checkpoint_data` stores a validated, versioned application plan and illustration brief. It is first-write/immutable for the run.
- `provider`, `provider_request_id`, and `model_id` checkpoint the fal submission and are also first-write/immutable.
- A retry uses saved plan JSON; when a fal request ID exists it retrieves that request rather than submitting another.
- The fal network submission and Postgres request-ID checkpoint cannot be atomic. A crash between them can cause a duplicate billable submission on retry.
- Completion validates all data before a fenced transaction inserts stops/hero, updates result metadata, marks itinerary ready/run succeeded, clears the plan checkpoint, and clears the lease.
- Reconciliation scans due Postgres rows independently of Redis wake-ups. Exhausted work fails with `GENERATION_ATTEMPTS_EXHAUSTED`.

## Successful result invariant

A public `done` result requires:

- non-empty destination, title, and summary;
- planned date and IANA destination timezone;
- three to five ordered places, each with a map link;
- exactly one ready itinerary-level hero with app-owned `/media` URL, content type, dimensions, and alt text;
- no terminal error.

`GET` never exposes fingerprints, idempotency hashes, evidence JSON, Cala entity IDs, generation runs, checkpoints, leases, raw provider data, storage filesystem paths, or provider diagnostics.

## Open production decisions

- Object-storage schema/public origin, retention/deletion, and ACLs.
- Data retention without accounts.
- Provider usage/cost detail and duplicate-submission monitoring.
- Recommendation algorithm implementation/versioning and activity-image source policy.

See [API contract](api-contract.md), [ADR 0003](decisions/0003-generation-lifecycle.md), [ADR 0004](decisions/0004-natural-request-and-journal-artifact.md), [ADR 0005](decisions/0005-city-and-tags-input.md), and [ADR 0006](decisions/0006-preference-learning-before-generation.md).
