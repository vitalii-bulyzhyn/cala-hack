# 0007: Provider-free demo generation

- Status: Accepted
- Date: 2026-08-29
- Supersedes: the missing-configuration subsection of [ADR 0004](0004-natural-request-and-journal-artifact.md)

## Context

The complete input → preference learning → journal flow must be testable on a fresh checkout without OpenAI, Cala, or fal credentials. The previous behavior accepted the request but terminally failed after learning, which prevented product and UI testing from reaching the main journal result.

## Decision

- `OFFLINE_DEMO_ENABLED` defaults to `true` for the repository and Compose setup.
- When any required generation-provider key is absent and demo mode is enabled, the worker selects a deterministic application-owned demo pipeline and contacts no external provider.
- The demo pipeline uses city, tags, and liked activity snapshots to produce three or four explicitly illustrative schedule entries, map-search links, a UTC timezone, and the same fixed creation-date-plus-seven-days rule.
- The supplied paper JPEG is bundled with the backend, copied atomically into itinerary-scoped app media, and persisted as the one ready hero required by the public `done` invariant.
- Compose runs a one-shot local media initializer so the non-root API/worker user can write the shared named volume.
- The result summary and frontend caption label this output as an offline sample rather than grounded provider output.
- When all provider keys exist, the Cala/OpenAI/fal pipeline remains the selected path.
- Operators can set `OFFLINE_DEMO_ENABLED=false` to retain `PROVIDER_CONFIGURATION_MISSING` as the terminal behavior for incomplete provider configuration.

## Consequences

- A credential-free local run now reaches `done`, so the full product and smoke lifecycle are non-billable and reproducible.
- Demo places are illustrative activities and map searches, not grounded venue recommendations; the UI and payload copy must not imply otherwise.
- The public result schema, durable lifecycle, lease/fencing rules, and app-owned media invariant stay unchanged.
- Production must disable demo fallback unless serving clearly labeled sample output is intentional.

## Alternatives considered

### Stop after preference learning

Rejected because it still prevents testing the generation, polling, media, and result-rendering states.

### Return a frontend-only fixture

Rejected because it would bypass the actual worker, Postgres completion, media serving, and public API contract that need end-to-end coverage.

### Require local mock-provider scripts

Rejected because the requested baseline must work without additional services or configuration.
