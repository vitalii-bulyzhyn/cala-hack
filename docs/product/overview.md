# Product overview

Status: City/tag creation, catalog-backed preference learning, downstream generation, and the integrated traveler-facing flow are **Current**. Production deployment/storage and broader browser automation remain **Open**.

## Product promise

Given a destination city and initial tags, Travel Journal learns from a short sequence of visual activity choices, then creates a grounded one-day plan and hand-drawn journal image. The result also exposes structured, ordered place details and usable links outside the image.

The product is travel inspiration. It is not a booking service, navigation tool, or guarantee of live hours, availability, prices, accessibility, or journey times.

## User and job

The initial user knows roughly where and how they want to spend a day but does not want to research, verify, arrange, and visualize it manually.

Their job is: “Turn this idea for a day away into a believable plan I can understand and get excited about.”

Example input:

- City: `Barcelona`
- Tags: `art`, `old streets`, `local food`, `relaxed pace`

## Current core flow

1. The user chooses Barcelona, Toulouse, or Valencia and submits zero to twenty preference tags.
2. The API persists a durable resource in `learning_preferences` and returns its ID.
3. The frontend requests the next preference page. The first algorithm call supplies three pairs (six activities); later pages may show one activity across a spread or a pair, one per page.
4. Every issued activity is stored with name, category, journal prose, optional media, and private grounding metadata. Full-page feedback atomically updates exact-item responses and reconstructs durable bandit state.
5. The UI automatically requests one Thompson-selected adaptive page after issuing the initial six, using prior arms if the traveler has not rated anything. From the final preference face, the user can complete with zero, partial, or complete responses. Completion finalizes state and creates the worker run under one session lock.
6. The worker uses city, tags, selected activities, and rejected activities while researching/planning, then checkpoints and illustrates the journal as before.
7. The user receives either `done` with one journal image and linked places, or `fail` with a safe error.

See [Architecture overview](../architecture/overview.md) for the durable sequence and [Experience](experience.md) for the current UI.

## Product principles

### Visual delight, structured truth

The journal image is the emotional artifact, not the only carrier of information. Destination, date, summary, schedule, locations, and links remain structured HTML-readable data. The image uses short labels rather than dense itinerary text.

### Grounded before eloquent

Cala supplies place research. OpenAI may select and phrase only supported place data; verified `official` and `source` URLs must occur verbatim in Cala evidence. Every place also gets an app-created map-search link.

### Deterministic date

The planned day is seven days after the immutable UTC date on which the resource was created. Date selection is not part of the current create contract.

### Learn before generating

Generation never starts at initial submission. Stable issued-item IDs make reload/retry show the same choice, while explicit completion may proceed with no votes: recorded likes/dislikes shape generation and unanswered entries remain neutral. The default algorithm strictly uses the selected city's food, culture, outdoors, and neighbourhoods journal entries; it ranks locally, can use OpenAI only to rerank unseen adaptive choices, and uses persisted Thompson-sampling arms to choose adaptive categories.

### Honest terminal outcomes

The plan and the hero image are both core. Missing providers select the labeled offline demo by default. In the live pipeline, an invalid plan, unsafe/failed image, exhausted retry, or media-copy failure produces `fail`; the API never labels incomplete output `done`.

### Durable progress without provider leakage

Public status stays `pending`, `done`, or `fail`; a pending `stage` gives useful product language. Provider request IDs, raw evidence, leases, attempts, and checkpoint payloads remain private.

## Success signals

- A supported city/tag input creates a durable learning session; the algorithm can issue six initial options and record every response.
- Completing learning creates exactly one generation run that receives the selected/rejected activity snapshot.
- The result has a resolved destination, planned date, IANA timezone, title, summary, three to five non-overlapping places, one map link per place, and exactly one app-owned hero image.
- Every verified link is grounded in Cala output, and no unsupported live claim is presented as fact.
- Retries reuse saved plan and fal-request checkpoints after they commit.
- The result remains understandable without reading text rendered into the image.
- The demo can be repeated with known credentials, bounded cost, and diagnosable safe failures.

## Glossary

- **Itinerary resource** — durable city/tag request and preference-learning owner, identified by UUID.
- **Public status** — `pending`, `done`, or `fail`.
- **Pending stage** — `learning_preferences`, `queued`, `researching`, `planning`, or `illustrating` while status is `pending`.
- **Preference page** — one journal opening with a `single` or `pair` activity layout.
- **Preference entry** — immutable displayed activity JSON with ID, image link, name, category, and description.
- **Place** — an ordered local-time stop with structured details and typed links.
- **Journal image** — the single itinerary-level hero copied into app-owned media storage.
- **Plan checkpoint** — immutable application-owned plan used to resume after research/planning.
- **Image checkpoint** — persisted fal provider/model/request ID used to resume retrieval without resubmission.

Implementation status is sequenced in the [Delivery plan](delivery-plan.md).
