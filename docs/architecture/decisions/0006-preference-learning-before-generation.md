# 0006: Preference learning before generation

- Status: Accepted
- Date: 2026-08-29
- Extends: [ADR 0005](0005-city-and-tags-input.md)

## Context

City and user-created tags are useful but too coarse for the revised experience. After creating an itinerary, the product presents visual activity choices and records like/dislike responses before generating the final plan. The recommendation developer supplied three conceptual operations: create three initial activity pairs, propose a later single/pair page from selected and rejected activities, and update the learning algorithm.

Generation previously started in the create transaction, so it could finish before this learning flow. Options and responses also need stable IDs and durable ownership so retries, reloads, and concurrent clicks cannot disconnect a response from what the user saw.

## Decision

- Creation persists city, tags, and a collecting preference-learning session. It returns the itinerary ID but creates no generation run.
- Internal itinerary stage `learning_preferences` projects publicly to `pending`.
- The algorithm is an application-owned async protocol with deterministic initial selection and state-aware adaptive selection.
- The default `city-journal-bandit-v1` implementation loads the exact authoritative Barcelona, Toulouse, or Valencia inventory covering food, culture, outdoors, and neighbourhoods. Initial selection is deterministic for city/tags and covers all four categories. Unsupported cities are rejected; there is no generic fallback.
- Page feedback is one atomic `PUT`. Supplied items must belong to the page; `like|dislike` responses are upserted and null responses are removed. Every write reconstructs a version-1 four-arm state from durable responses, starting from `alpha=1,beta=1` priors.
- Likes add `1.0` to alpha. Initial/adaptive dislikes add `0.25`/`0.5` to beta. Neutral items add no evidence, so retries and edits cannot double-count.
- After six explicit initial answers it can return one persisted single/pair adaptive page. It optionally asks OpenAI to rerank unseen catalog names within their existing categories; any missing key/provider/model error falls back to deterministic local ranking. Thompson Sampling chooses among non-exhausted categories and chooses two with probability `0.35`.
- The first next-page request requires exactly three two-entry initial pages: six activities total.
- Later pages contain one or two activities and expose `layout: single|pair`.
- Every activity is durably stored with its UUID, name, category, journal prose, optional HTTP(S) image link, and private nullable Cala entity metadata before it is returned. Current authoritative entries omit media and render as prose rather than using replacement stock imagery.
- Responses remain per-itinerary, per-item durable records but are mutated only through the page feedback operation. Learning is immutable after completion.
- Completion is an explicit traveler action and is allowed while any number of issued entries remain unanswered; an adaptive page is optional. Under the same session lock it reconstructs/finalizes state, closes the session, queues the itinerary, and creates exactly one version-4 orchestration run. Redis is notified only after commit.
- The worker receives selected and rejected activity snapshots alongside original city/tags. Provider planning treats them as untrusted preference data.
- Postgres remains authoritative. Redis still carries only the resulting generation-run UUID.

## Consequences

- Final generation cannot race ahead of learning.
- Reloaded clients retrieve issued pages with their decisions and can safely replay a full page update.
- Travelers can skip any or every activity without being blocked from generation; sparse learning falls back to the original city/tags and generation defaults.
- Future recommendation implementations have a narrow replaceable interface without changing public API or persistence.
- Preference learning works offline from authoritative per-city data; optional adaptive OpenAI use adds latency/cost only when configured.
- `GET .../preference-pages/next` has get-or-create behavior when a new algorithm page is needed. It is repeat-safe and non-cacheable, but it is not a strictly side-effect-free HTTP read.
- Page feedback cannot commit between the completion snapshot and session closure because both operations serialize on the learning-session row lock.
- A future non-null activity image remains external display media, not copied/generated journal media. The frontend must treat it as untrusted remote content.

## Alternatives considered

### Start the worker at itinerary creation

Rejected because learned responses would arrive after planning and could not influence the result.

### Store only selected/rejected activity names

Rejected because responses must remain tied to the exact immutable item shown, including its display metadata.

### Let the frontend supply algorithm activities

Rejected because it would move recommendation authority and validation into an untrusted client.

### Generate every activity dynamically

Rejected for the first implementation because it adds latency, nondeterminism, image sourcing, and malformed-output risk before the interaction can begin. A curated catalog provides stable JSON and OpenAI can safely rerank only known names.
