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
- The algorithm is an application-owned async protocol with `get_initial_pairs`, `get_next_page`, and `update_learning_algorithm`.
- The default `catalog-bandit-v1` implementation loads an extendable curated catalog covering food, drinks/party, culture, and nature. Initial selection is deterministic for city/tags and covers all four categories.
- After six answers it can return one single/pair adaptive page. It optionally asks OpenAI to rerank unseen catalog names within their existing categories; any missing key/provider/model error falls back to deterministic local ranking.
- The completion update hook is currently stateless because ranking learns online from the full durable response snapshot.
- The first next-page request requires exactly three two-entry initial pages: six activities total.
- Later pages contain one or two activities and expose `layout: single|pair`.
- Every activity is durably stored with its UUID, name, category, description, and HTTP(S) image link before it is returned.
- Responses are per-itinerary, per-item `like|dislike` upserts. Learning is immutable after completion.
- Completion is an explicit traveler action and is allowed while any number of issued entries remain unanswered; an adaptive page is optional. Recorded likes/dislikes are passed to the update hook and worker as selected/rejected snapshots, while unanswered entries are neutral and omitted. Completion closes the session, creates exactly one version-4 orchestration run, and best-effort notifies Redis after commit.
- The worker receives selected and rejected activity snapshots alongside original city/tags. Provider planning treats them as untrusted preference data.
- Postgres remains authoritative. Redis still carries only the resulting generation-run UUID.

## Consequences

- Final generation cannot race ahead of learning.
- Reloaded clients can retrieve the same unanswered page and safely repeat a decision.
- Travelers can skip any or every activity without being blocked from generation; sparse learning falls back to the original city/tags and generation defaults.
- Future recommendation implementations have a narrow replaceable interface without changing public API or persistence.
- Preference learning works offline from curated data; optional adaptive OpenAI use adds latency/cost only when configured.
- `GET .../preference-pages/next` has get-or-create behavior when a new algorithm page is needed. It is repeat-safe and non-cacheable, but it is not a strictly side-effect-free HTTP read.
- The algorithm update happens before the database completion commit. Implementations must tolerate a repeated update if a later database failure causes the client to retry.
- Activity image links are external display URLs, not copied/generated journal media. The frontend must treat them as untrusted remote content.

## Alternatives considered

### Start the worker at itinerary creation

Rejected because learned responses would arrive after planning and could not influence the result.

### Store only selected/rejected activity names

Rejected because responses must remain tied to the exact immutable item shown, including its display metadata.

### Let the frontend supply algorithm activities

Rejected because it would move recommendation authority and validation into an untrusted client.

### Generate every activity dynamically

Rejected for the first implementation because it adds latency, nondeterminism, image sourcing, and malformed-output risk before the interaction can begin. A curated catalog provides stable JSON and OpenAI can safely rerank only known names.
