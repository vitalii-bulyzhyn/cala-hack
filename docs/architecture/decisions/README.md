# Architecture decision records

This directory records consequential choices and tradeoffs. An accepted ADR describes the current direction. A later reversal supersedes it explicitly and links both records rather than silently erasing history.

## Decision index

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-monorepo-and-service-boundaries.md) | Accepted | One repository with frontend, backend, documentation, and root infrastructure. |
| [0002](0002-backend-owned-provider-access.md) | Accepted | Cala, OpenAI, and fal access stays inside the Python API/worker boundary. |
| [0003](0003-generation-lifecycle.md) | Accepted | Postgres-authoritative generation runs with Redis wake-ups, leases, fencing, reconciliation, and checkpoints. |
| [0004](0004-natural-request-and-journal-artifact.md) | Partially superseded | Three public states, complete linked-place result, and one app-owned journal hero remain accepted; ADR 0005 replaces input/date handling and ADR 0007 replaces missing-key behavior. |
| [0005](0005-city-and-tags-input.md) | Accepted | Required city plus tag-array input, separate persistence, semantic idempotency, and a fixed seven-day date. |
| [0006](0006-preference-learning-before-generation.md) | Accepted | Persist visual preference pages and responses before creating generation work. |
| [0007](0007-provider-free-demo-generation.md) | Accepted | Reach a complete, labeled, provider-free demo journal when credentials are absent. |

## When to add an ADR

Add an ADR when a change:

- moves responsibility between frontend, API, worker, database, queue, media storage, or provider;
- changes durable truth, checkpoint/retry semantics, or a public result invariant;
- introduces/replaces a major dependency;
- chooses production storage, job processing, or deployment topology;
- reverses an accepted decision.

Small implementation details and reversible refactors belong in code/review context.

## Template

```markdown
# NNNN: Short decision title

- Status: Proposed | Accepted | Superseded
- Date: YYYY-MM-DD
- Supersedes: optional ADR link

## Context

Why is a decision required?

## Decision

What will the system do?

## Consequences

What becomes easier, harder, or required?

## Alternatives considered

What credible options were rejected, and why?
```
