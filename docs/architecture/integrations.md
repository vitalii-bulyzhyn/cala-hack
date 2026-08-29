# External integrations

Status: Cala query/search, OpenAI Responses structured intent/plan, fal queue generation, fenced checkpoints, and app-owned media copy are **Current**.

All integrations are backend-only and return application-owned types. Provider SDK objects and raw payloads do not cross into route schemas, persisted public result fields, or frontend code.

## Responsibility map

| Boundary | Current responsibility | Must not be treated as |
| --- | --- | --- |
| Preference catalog/ranker | Produce six stable initial activities and one optional adaptive page | Live place inventory or final itinerary research |
| OpenAI intent | Resolve canonical destination and IANA timezone from untrusted city/tag/learned-choice data | Durable truth or permission to follow embedded instructions |
| Cala | Ground candidate places and source context through knowledge query and search | Live routing, hours, inventory, accessibility, or booking data |
| OpenAI plan | Select/sequence three to five Cala-grounded places and produce typed copy/location/link candidates | A source of invented URLs, coordinates, or live facts |
| fal | Generate exactly one illustrative 4:3 hero through its async queue | Permanent storage or a factual depiction guarantee |
| App media store | Copy validated provider bytes atomically and expose `/media/...` | Production object storage/CDN |

See [ADR 0002](decisions/0002-backend-owned-provider-access.md) for provider ownership, [ADR 0004](decisions/0004-natural-request-and-journal-artifact.md) for the artifact contract, [ADR 0005](decisions/0005-city-and-tags-input.md) for input ownership, and [ADR 0006](decisions/0006-preference-learning-before-generation.md) for learned-choice ownership.

## Preference activity ranking

`catalog-bandit-v1` loads `app/data/activities.json`, currently covering food, drinks/party, culture, and nature with at least four entries per category. City/tags deterministically rank the catalog and the first call selects six unique activities across all categories as three pairs.

After six answers, category like/dislike scores choose one or two categories for one adaptive page. With `OPENAI_API_KEY`, the Responses API may rerank only the supplied unseen activity names inside their existing categories using a strict application-owned schema. It may not rename, invent, omit, duplicate, or recategorize candidates. Any missing key, provider failure, or invalid ranking falls back to the deterministic local order. After the adaptive page is answered, the current algorithm returns no further page.

Catalog image links are validated display URLs and are returned to the frontend; this backend does not download or proxy them. They are distinct from the generated journal image and its app-owned media-copy guarantees.

## OpenAI intent and planning

The worker uses the server-side OpenAI SDK and Responses API twice:

1. Resolve stored city/tag data and selected/rejected activity snapshots into `TripIntent`: valid-destination flag, canonical destination, IANA timezone, deterministic planned date, and stored tags as base preferences.
2. After Cala research, parse a schema-constrained `ModelItineraryPlan`: title, summary, and three to five typed places.

Both calls use application-owned Pydantic Structured Outputs, `store=false`, explicit token limits, safe error mapping, and a configured timeout. The result passes application validation before checkpointing or persistence.

Intent instructions receive the immutable UTC creation-date reference and enforce:

- reference date plus seven days as the current fixed planned date;
- stored tags copied as base preferences rather than model-invented preferences;
- selected/rejected activities supplied as separate untrusted planning context, without their image URLs;
- valid destination text and IANA timezone;
- rejection of invalid/ambiguous cities and embedded prompt-changing instructions in city or tags.

Plan instructions treat serialized Cala output as untrusted data, use English concise copy, require three to five non-overlapping local-time places, and prohibit invented operational facts. Addresses, coordinates, entity IDs, and URLs are nullable/omitted when unsupported.

The configured model ID is replaceable. `gpt-5.6-terra` is the current scaffold default, not a permanent product decision. Official guidance: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [migrating to Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses).

## Cala research

Current service details:

- Base URL `https://api.cala.ai`.
- Authentication header `X-API-KEY`.
- `POST /v1/knowledge/query` for structured result/entity data.
- `POST /v1/knowledge/search` for sourced narrative context.

The worker runs query and search concurrently after intent resolution. It asks for five to eight visitable candidates, exact names/category/location/entity identifiers, and official/source URLs when known. Empty or invalid combined research fails rather than producing an ungrounded plan.

Before checkpointing the plan:

- `official` and `source` URLs must occur verbatim in the serialized Cala response;
- Cala entity IDs are retained only if found in returned entity data;
- any unsupported coordinate pair is removed;
- raw Cala data is used only as private planning input; selected verified URLs/evidence are normalized into the checkpoint and persistence, never exposed as a provider payload;
- the research timestamp is saved with evidence.

Every place also gets a Google Maps search URL constructed by the application from name, supported address, and destination. It is typed `map` and is not a claim about a live route.

Reference: [Cala quickstart](https://docs.cala.ai/quickstart).

## Application plan checkpoint

After intent, research, OpenAI planning, link verification, schedule validation, and illustration-brief construction, the worker saves one versioned application-owned checkpoint. It includes destination/date/timezone, title/summary, places/evidence/links, research timestamp, the fal illustration prompt, and hero alt text.

The write is lease/fence protected and first-write/immutable. Retries validate and reuse it, so a transient image failure does not repeat Cala/OpenAI or change the planned day.

## fal image generation

The worker submits one request through fal's asynchronous queue with:

- configured `FAL_IMAGE_MODEL`;
- one deterministic itinerary-derived seed;
- `landscape_4_3`, one image, JPEG output;
- safety checker enabled;
- short labels only, no paragraphs, prices, schedules, logos, or photorealism;
- a provider lifecycle preference of 24 hours for the temporary source object.

Immediately after submission returns, the worker saves provider `fal`, model ID, and request ID behind the same run lease/fence. On retry, an existing checkpoint uses `get_handle(model, request_id)` and waits for that request instead of submitting again.

The network submission and Postgres checkpoint cannot be one atomic transaction. If the worker crashes after fal accepts the request but before the ID commits, a retry may submit a duplicate and incur duplicate cost. Once checkpointed, the request ID is immutable and resumable. Timeouts/rate limits/provider failures use bounded retry classification.

The provider result must contain exactly one safe image with HTTPS URL, supported content type, and positive width/height. The app never exposes the fal URL as the successful public artifact.

References: [fal asynchronous inference](https://fal.ai/docs/documentation/model-apis/inference/queue) and [fal CDN retention/access](https://fal.ai/docs/documentation/model-apis/fal-cdn).

## App-owned media copy

After fal completion, the worker streams the temporary HTTPS image into storage controlled by this application:

- supported types: JPEG, PNG, WebP, AVIF;
- HTTPS only; malformed/credential-bearing/local/loopback/non-global-IP targets are rejected before transfer;
- default-client DNS answers are screened for non-global addresses, redirects are disabled at the client and each hop is revalidated (maximum five);
- configurable download timeout and maximum byte count;
- detected image magic bytes must match a supported MIME declaration/expectation;
- itinerary-scoped key `<itinerary-id>/journal.<ext>`;
- temporary file plus atomic replacement;
- public relative URL below configured `/media`.

Compose mounts the same `generated_media` volume into worker and API. Host processes default to `.data/generated-media`. The API creates/mounts the directory and serves it with FastAPI static files.

Malformed URLs, unsafe redirects/addresses, invalid content, and filesystem failures map to safe application errors; retryability is explicit. This removes dependency on fal URL expiry for a completed local/demo result. It does not solve multi-host replication, backup, CDN delivery, retention, deletion, authentication, or production ACLs; those require object storage.

## Error and configuration contract

- All three keys are optional at process startup and readiness.
- When any key is absent, the worker uses an unconfigured pipeline and terminally records `PROVIDER_CONFIGURATION_MISSING` without contacting a provider.
- Provider configuration status reports presence only and reveals no secret fragment.
- Provider connection/timeouts, rate limits, invalid/refused/incomplete output, safety rejection, and media-copy failures become stable safe codes with retry classification.
- Retryable failures use the durable run attempt limit/backoff. A required failure after exhaustion produces public `fail`; no public partial result exists.
- Liveness never calls dependencies. Readiness calls Postgres/Redis only; it never spends provider quota.

## Shared adapter rules

- Explicit timeouts and bounded payload/context sizes.
- No raw prompt/provider body or credential in logs, errors, checkpoints exposed to clients, or test snapshots.
- Correlate application request/run ID and provider request ID without returning internal diagnostics publicly.
- Test doubles require no network/key; live tests are separately invoked and explicitly billable.
- Record model/prompt/schema versions, latency, attempts, and usage/cost inputs where available.
- Validate again at every provider, checkpoint, persistence, and public-projection boundary.

The durable sequence is in [Architecture overview](overview.md); physical state is in [Domain model](domain-model.md).
