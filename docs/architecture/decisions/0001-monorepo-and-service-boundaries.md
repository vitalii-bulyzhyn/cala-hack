# 0001: Monorepo and service boundaries

- Status: Accepted
- Date: 2026-08-29

## Context

The hackathon team needs a frontend, backend, local infrastructure, and shared product/technical documentation that can evolve together. Setup must remain easy for humans and coding agents, and cross-service changes should be reviewable as one unit.

## Decision

Use one repository with these top-level responsibilities:

- `dev/frontend` — Next.js frontend.
- `dev/backend` — FastAPI backend.
- `docs` — product, architecture, decisions, and engineering guidance.
- Root Compose, environment example, and Make targets — shared local orchestration.
- Root `AGENTS.md` — a concise navigation map, not a duplicate handbook.

The default Compose workflow runs six long-running services—frontend, backend, worker, Postgres, Redis, and pgAdmin—after a one-shot `migrate` service succeeds. `make infra-up` supports a second workflow in which only infrastructure runs in Docker and the frontend, API, and worker run on the host. Each app retains its own dependency manifest.

## Consequences

- A single change can update contracts, both applications, and documentation atomically.
- Root commands provide a predictable entry point for contributors.
- App-specific dependencies remain isolated in `dev/frontend` and `dev/backend`.
- Repository-wide checks need to coordinate npm, Python, and Compose tooling.
- Documentation ownership must be explicit to prevent duplicate, drifting setup guides.

## Alternatives considered

### Separate frontend and backend repositories

Rejected for the hackathon because contract and setup changes would require cross-repository coordination with little immediate benefit.

### Put application code at the repository root

Rejected because two runtimes, shared infrastructure, and documentation need clear boundaries.

### Put implementation detail in `AGENTS.md`

Rejected because a large agent file becomes stale and hard to navigate. It should route readers to canonical documents instead.
