# 0005: City and tags input

- Status: Accepted
- Date: 2026-08-29
- Supersedes: Request/date interpretation in [ADR 0004](0004-natural-request-and-journal-artifact.md)

## Context

The product form now collects a destination city and reusable preference tags rather than an open-ended natural-language sentence. Those values need distinct validation, durable fields, idempotency behavior, and worker inputs. The create contract no longer contains a travel date.

## Decision

- `POST /api/v1/itineraries` requires exactly `city` and `tags`.
- City is cleaned human text with a 160-character limit.
- Tags is a required array that may be empty, contains at most 20 cleaned labels of at most 50 characters, and is case-insensitively deduplicated while preserving first occurrence order.
- Postgres stores `city` and JSONB `tags` in separate itinerary columns. Revision `20260829_0003` migrates existing rows and removes `request_text`.
- `GET` returns the stored city and tags at the resource top level in every state.
- The version-3 idempotency fingerprint normalizes city case and treats tag case, order, and duplicates as semantically equivalent. The first accepted request retains its display casing/order.
- After ADR 0006 preference completion, worker tasks receive city/tags plus selected/rejected activity snapshots. OpenAI resolves canonical destination/timezone while stored tags remain base preferences.
- Planned date is always the immutable UTC creation date plus seven days. Date input is outside the current contract.
- New runs/checkpoints use orchestration version 3 and `city-tags-itinerary-v1` so they cannot silently reuse the retired input interpretation.

## Consequences

- The form and API become predictable and easy to validate.
- Tags remain queryable as one durable JSONB field without mixing them into city text.
- Reordered or differently cased equivalent tags do not create an idempotency conflict.
- Rich free-form intent and user-selected dates are no longer expressible; adding either requires an explicit contract revision.
- Existing revision-0002 rows are backfilled with resolved destination when available, otherwise their prior request text truncated to the city limit; their tags default to empty.

## Alternatives considered

### Keep one natural-language request

Rejected because the current frontend/product contract explicitly separates destination and preferences.

### Store tags inside city or a concatenated request string

Rejected because it prevents independent validation, faithful API projection, and future tag filtering.

### Treat tag order as idempotency-significant

Rejected because order does not change planning intent and would create surprising conflicts for equivalent inputs.

### Ask OpenAI to invent or rewrite tags

Rejected because stored user selections are the source of truth for preferences.
