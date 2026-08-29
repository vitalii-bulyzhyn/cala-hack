# Security and privacy

Status: Backend-only credentials, validated city/tag/activity input, durable preference responses, grounded links, hashed idempotency, Postgres fencing/checkpoints, UUID-only Redis hints, and bounded media copy are the **Current** baseline. Public-production controls are **Proposed**.

This is a hackathon implementation, not a production security claim.

## Current baseline

- OpenAI, Cala, fal, database, Redis, and pgAdmin credentials are server-side environment values.
- `/api/v1/providers/status` reports configuration presence without values/fragments or provider calls.
- City, tags, and algorithm activity copy are NFKC-normalized, whitespace-collapsed, length/control/letter validated, and stored for the resource.
- Preference image links must be HTTP(S), but are display links and are not downloaded by the backend. The recommendation implementation must use an approved image source policy.
- Raw idempotency keys are never stored; only SHA-256 hashes and versioned request fingerprints remain.
- Redis entries contain generation-run UUIDs only. Requests, prompts, plans, provider IDs, leases, and results stay in Postgres/application storage.
- Checkpoint and terminal writes require current owner, fence version, running state, and unexpired lease.
- Cala data and user text are treated as untrusted input to fixed Structured Output instructions.
- Official/source links must occur in Cala research; map links are constructed from encoded application data.
- fal output must be one HTTPS image with validated type/dimensions. The copy rejects malformed/local/loopback/private targets, screens default-client DNS, revalidates every bounded redirect hop, checks magic bytes against MIME, enforces size/time limits, maps filesystem failures safely, and writes atomically under an itinerary-scoped path.
- Successful public image URLs point to app storage, not fal.
- Missing provider keys select a clearly labeled, network-free demo pipeline by default; disabling demo mode restores safe `PROVIDER_CONFIGURATION_MISSING`.
- pgAdmin and local media serving are development/demo facilities.

## Data classification

| Data | Treatment |
| --- | --- |
| City and preference tags | Stored user content; may contain personal preferences or accidental PII. Minimize retention and warn users not to include sensitive data. |
| Issued activities and like/dislike responses | Behavioral preference data tied to an itinerary. Treat as potentially sensitive profiling data; minimize retention and access. |
| Destination/date/timezone | Travel-planning data; not identity by itself but potentially sensitive in combination. |
| Plan/place copy | Model-generated and potentially inaccurate; ground and label limitations. |
| Cala evidence/entity IDs | Private grounding/diagnostic data; expose only approved typed links. |
| Idempotency fingerprint/hash | Internal metadata; never return or log raw values. |
| Run/lease/checkpoint data | Internal operational state; expose only public status/stage/safe error. |
| Provider request IDs/usage | Internal diagnostics and cost data. |
| Journal image | Generated, publicly readable locally below `/media`; must contain no secrets/PII. |
| API keys/auth headers/DSNs | Secrets; never return, persist in domain content, or log. |

Do not collect names, email, exact home/current location, travel documents, payments, or other sensitive personal data for the MVP.

## Threats and controls

### Secret disclosure

- Keep provider calls inside Python API/worker adapters; never call them from browser/Next.js code.
- Redact credentials, authorization headers, full DSNs, raw prompts/provider bodies, and checkpoint content.
- Scan commits/CI output and rotate any leaked credential immediately.

### Cost and duplicate side effects

- Add public request rate limits, per-itinerary/provider caps, and an emergency disable switch before exposure.
- Keep bounded attempts/timeouts/output/context/image size.
- Persist the application plan and fal request ID immediately behind the worker fence; reuse them on retry.
- Recognize the unavoidable crash after fal acceptance but before request-ID commit. It can create a duplicate billable submission; instrument/alert and use provider idempotency if later supported.
- Do not run configured smoke tests casually in shared CI.

### Prompt injection and untrusted provider data

- Treat city/tags, selected/rejected activity copy, and Cala content as data, not instructions.
- Keep fixed developer instructions separate and require strict application-owned Structured Outputs.
- Do not let input/research choose models, tools, URLs to fetch, storage paths, database actions, or secrets.
- Validate destination/timezone/date, plan order/times, fields, entity IDs, links, and final media again outside the model.
- Escape generated copy through normal framework rendering; never inject model HTML.

### Incorrect travel claims and unsafe links

- Never imply Cala knowledge is live hours, pricing, availability, accessibility, wait time, or routing.
- Admit `official`/`source` URLs only by exact match to research and validate HTTP(S) shape/no embedded credentials.
- Treat the generated Google Maps URL as a search link, not proof of identity or route duration.
- Add outbound-link safety attributes and clearly label link kinds in the frontend.
- Encourage verification of time-sensitive details.

### Media download/storage

- Download only the validated fal result; reject credentials/local/non-global addresses, screen DNS, and revalidate every redirect hop.
- Require supported image magic bytes consistent with MIME/expected type, enforce byte/time limits, and use atomic writes under a resolved storage root.
- Map HTTP/network/filesystem failures to sanitized codes with deliberate retry classification.
- Keep generated prompts/images free of secrets and unnecessary personal data.
- Local `/media` files have no authentication and shared-volume durability only; do not promise private/permanent journals.
- Before production, add malware/content scanning as appropriate, object storage, ACLs, signed/public URL policy, retention/deletion, backup, cleanup, and infrastructure-level egress policy as defense in depth.

### Infrastructure and worker integrity

- Bind Postgres, Redis, pgAdmin, and local media for development appropriately; do not expose admin/data services publicly.
- Perform all state/checkpoint changes through Postgres claim/lease/fencing operations.
- Treat Redis UUIDs as untrusted hints and parse defensively; do not treat heartbeat as job progress.
- Keep worker replica/concurrency and shared-media semantics explicit before scaling beyond one worker/host.
- Use production TLS, exact CORS, least privilege, managed secrets, backups, and network isolation.

## Logging rules

Allowed structured fields include application request ID, itinerary/run ID, worker ID, public/internal stage/status, provider name, provider request ID, configured model/prompt/schema version, duration, attempt, fence version, safe error code, and aggregate usage.

Do not log credentials, raw idempotency keys/hashes, authorization headers, full DSNs, full city/tag/activity input or prompts by default, individual preference responses, raw provider responses, checkpoint JSON, cookies, or client-visible stack traces.

## Required before public deployment

- Rate limiting, cost ceilings, abuse monitoring, and provider disable controls.
- Authentication/sharing decision and data/media retention/deletion policy.
- Production object storage/CDN and access/public-URL decision.
- Media/content-safety review, infrastructure egress policy, and storage cleanup.
- Production CORS, TLS, network isolation, backups, least privilege, and secret management.
- Dependency/container vulnerability checks and user-facing factual limitations.

See [Configuration](configuration.md), [External integrations](../architecture/integrations.md), and [product risks](../product/scope.md#primary-risks-and-mitigations).
