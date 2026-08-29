# 0004: Natural request and complete journal artifact

- Status: Accepted; input/date portion superseded by [ADR 0005](0005-city-and-tags-input.md)
- Date: 2026-08-29

## Context

The product must accept richer intent than a city field while keeping the frontend contract small. The final experience is one visually compelling journal image, but place details and links must remain accessible, grounded, and testable. Partial plans/images complicate both truthfulness and the demo state model.

## Decision

The request/date interpretation subsection below records the original decision and is no longer current. ADR 0005 replaces it with separate city/tag fields and a fixed date; ADR 0006 adds `learning_preferences` before queued generation. The result-artifact, provider, media, and missing-configuration decisions remain accepted.

### Request and date interpretation

- Accept one provider-neutral `request` string, cleaned and limited to 1–1,000 characters.
- Preserve the original cleaned request on the durable resource.
- Use the itinerary's immutable UTC creation date as the reference on every worker attempt.
- “Next week” without a weekday resolves to Monday of the next ISO week; no date resolves to reference plus seven days.
- The backend resolves a canonical display destination, exact date, and IANA destination timezone.

### Public lifecycle

- Expose only `pending`, `done`, and `fail`.
- While pending, `stage` is one of `learning_preferences`, `queued`, `researching`, `planning`, or `illustrating`; terminal stage is `null`.
- `result` is non-null only for `done`; `error` is non-null only for `fail`.
- There is no public partial state. Core plan, image generation, and app-owned media copy are all required.

### Result artifact

A done result contains:

- destination, planned date, destination timezone, title, and summary;
- three to five ordered, consecutive, non-overlapping local-time places;
- structured place copy/location and typed links;
- exactly one ready itinerary-level hero image with app-owned URL, type, dimensions, and alt text.

Every place has an app-created `map` link. `official` and `source` links are admitted only when their exact URL occurs in Cala research. The generated image uses short labels; essential itinerary content stays structured outside it.

### Provider sequence

- OpenAI Responses Structured Output interprets untrusted trip intent.
- Cala knowledge query and search ground candidates/context.
- OpenAI Responses Structured Output creates the validated plan from that research.
- fal's async queue creates one 4:3 hero from an application-owned brief.

The application plan and fal request ID are durable fenced checkpoints as defined by [ADR 0003](0003-generation-lifecycle.md).

### Media ownership

- The worker copies a valid fal image into shared app-owned local storage before success.
- The API serves the copied artifact below `/media`; a done response never depends on a fal URL.
- Shared local storage is accepted for the hackathon. Production object storage/CDN, retention, deletion, and ACLs remain open.

### Missing configuration

OpenAI, Cala, and fal keys are optional for process boot/readiness. A submitted job without all required keys terminates as `fail` with `PROVIDER_CONFIGURATION_MISSING` and calls no provider.

## Consequences

- Natural language carries destination, date, and preferences without expanding the form schema.
- The public state machine and frontend polling remain small while internal stages/retries stay expressive.
- A done response is atomic and useful without reading generated-image text.
- Requiring the hero means an image failure fails the job even if a private plan exists.
- Link grounding is auditable, while map URLs are clearly app-created search links rather than evidence.
- Local media survives fal expiry but is not multi-host/production durable.
- Date defaults are deterministic across delayed retries.

## Alternatives considered

### Keep a city-only field

Rejected because it cannot express date, pace, interests, or tone without immediate schema growth.

### Expose every internal lifecycle state as public status

Rejected because it couples clients to worker implementation. Stable pending stage provides enough feedback.

### Publish text-only or partial success after image failure

Rejected for this product/demo contract: the single journal artifact is core, so incomplete output is `fail`.

### Put the itinerary only inside the generated image

Rejected because generated text is not a reliable, accessible, linkable, or testable source of truth.

### Return the fal CDN URL

Rejected because provider retention/access can expire or change. The app copies the artifact before `done`.

### Generate one image per place

Rejected for the hackathon because it multiplies latency, cost, failure states, and layout complexity.
