# Product scope

Status: City/tag persistence, preference-learning persistence/APIs, provider-free and provider-backed generation, polling, linked places, app-owned local media, and the integrated frontend are **Current**. Production operations remain open.

## Confirmed scope

- Input: Barcelona, Toulouse, or Valencia, plus a required array of zero to twenty preference tags, each 1–50 characters.
- Learning: three initial two-activity pages (six choices), optional later one/two-activity pages, and durable like/dislike responses.
- Output: one future/current one-day itinerary with three to five ordered places.
- Presentation: one landscape 4:3, hand-drawn journal image plus structured place data and links.
- Platform: web application using Next.js and FastAPI.
- Services: Postgres and Redis locally; Cala, OpenAI, and fal are optional for the grounded/generated path.

## Current backend behavior

- `POST /api/v1/itineraries` cleans/persists `city` and `tags`, creates a collecting learning session without generation work, and returns the durable ID. Optional idempotency keys are hashed.
- Preference APIs get-or-create the next page, atomically replace page feedback, and complete learning. Completion creates the one generation run.
- `city-journal-bandit-v1` selects six unique initial entries from the chosen city's food, culture, outdoors, and neighbourhoods inventory, then may issue one adaptive single/pair page using persisted Thompson Sampling. OpenAI reranking is optional and falls back locally; unsupported cities never receive substitute content.
- `GET /api/v1/itineraries/{id}` exposes only `pending`, `done`, or `fail`; `stage` is non-null only while pending, `result` only when done, and `error` only when failed.
- Without provider credentials, a labeled deterministic demo uses the stored city, selected activities, UTC, map searches, and the same seven-day date so the full product remains testable.
- With all credentials, OpenAI resolves the canonical destination and IANA timezone. Stored tags plus selected/rejected activity snapshots guide planning; the date is seven days after immutable creation.
- Cala knowledge query and search provide place candidates and evidence. A second OpenAI Responses structured output creates three to five non-overlapping places.
- The worker checkpoints the application plan and fal request ID behind its lease/fence, generates exactly one hero, copies it into app-owned storage, and completes atomically.
- Every place has a generated map-search link. `official` and `source` links must match URLs present in Cala research.
- Missing provider credentials select a labeled offline demo by default, keeping the complete input/preferences/journal flow testable without network provider calls.
- Any required provider, plan, image, or media-storage failure produces `fail`; no public partial result exists.

The exact [API contract](../architecture/api-contract.md) and [domain model](../architecture/domain-model.md) are canonical.

## Date rules

1. The planned date is the immutable UTC creation date plus seven days.
2. Worker retries reuse that same reference date and cannot drift the result.
3. Place time windows are local to `destination_timezone` and use `HH:MM`.

## MVP acceptance criteria

1. A user can submit a valid city and tag array and poll the returned resource.
2. A configured preference engine can return six initial entries, each with image link/name/category/description, and store like/dislike by itinerary/item.
3. Single/pair layouts are explicit, page turns do not require a response, and explicit completion can create generation work with zero, partial, or complete recorded preferences.
4. Pending UI copy reflects `learning_preferences`, `queued`, `researching`, `planning`, or `illustrating` without exposing providers.
5. A `done` result contains all required destination metadata, three to five consecutive/non-overlapping places, and one ready hero image.
6. Place links are typed as `map`, `official`, or `source`; every place has a map link and verified links are traceable to Cala research.
7. Structured place content remains readable and operable outside the generated image.
8. A required-stage failure produces a stable error code, safe message, request ID, and retryability flag.
9. Retry resumes committed plan and fal checkpoints; stale workers cannot overwrite them.
10. The result remains understandable on narrow screens and by keyboard/screen-reader users.

## Non-goals for the hackathon MVP

- Multi-day trips, hotels, flights, cross-city planning, booking, payment, or ticketing.
- Accounts, social collaboration, saved-history guarantees, or permanent public sharing.
- Live hours, inventory, queue lengths, transit conditions, or turn-by-turn navigation.
- Interactive clarification, cancellation, server-sent events, or arbitrary itinerary editing.
- Public partial results or per-stop generated illustrations.
- Production-scale worker fleets, production SLA, or full analytics/localization.
- Treating local media storage as a production object-storage solution.

## Primary risks and mitigations

| Risk | Impact | Current/required mitigation |
| --- | --- | --- |
| Stale or invented facts | Misleading advice | Cala grounding, strict structured output, exact-URL verification, and no live operational claims. |
| Ambiguous or malicious city/tag input | Wrong trip or prompt injection | Length/control validation, schema-based destination resolution, fixed instructions, and deterministic failure. |
| Sensitive behavioral preferences | Unwanted profiling/exposure | Itinerary-scoped storage, no public response projection, retention decision before production, and no response logging. |
| Unsafe/broken activity image URLs | Tracking, broken preference UI | HTTP(S)/length validation now; approved hosts/proxy/retention policy required with the algorithm implementation. |
| Provider latency/quota | Long pending state or cost | Timeouts, bounded attempts/backoff, persistent checkpoints, and visible stages. |
| fal submit/checkpoint crash | Possible duplicate billable image | Persist request ID immediately, resume once saved, document the unavoidable pre-commit window, and monitor duplicates. |
| Expiring provider media | Broken result | Copy successful fal output into app-owned storage before `done`. |
| Local storage loss/scaling | Missing images across deployments | Shared local volume for demo; choose production object storage before deployment. |
| Generated-image text quality | Confusing plan | Short labels only; keep all essential itinerary data structured outside the image. |
| Secret leakage/public abuse | Compromised account or spend | Backend-only credentials, redaction, rate/cost limits before public exposure. |

See [Security](../engineering/security.md) for the complete control baseline.

## Open decisions

- Final OpenAI and fal model IDs and per-itinerary latency/cost ceiling; current IDs are replaceable configuration defaults.
- Production object storage, public URL strategy, retention, deletion, and access control.
- Deployment target, production CORS/network topology, authentication/sharing, and rate limiting.
- Minimum Cala coverage and fallback behavior for weak destinations.
- Recommendation algorithm/version, stopping rule, season/food-tag interpretation, and approved activity-image source.
- Final frontend brand, typography, responsive composition, and source-link treatment.

These decisions do not alter the current public contract. They are attached to the [Delivery plan](delivery-plan.md).
