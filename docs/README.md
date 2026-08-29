# Documentation

Status: The integrated frontend, city/tag and catalog-backed preference-learning APIs, three-state polling, worker/provider pipeline, checkpoints, and app-owned local media are **Current**. Production deployment/storage remain **Open**.

Use this index instead of treating `AGENTS.md` as a specification.

## Product

- [Overview](product/overview.md) — product promise, user job, flow, principles, and success signals.
- [Scope](product/scope.md) — implemented backend behavior, MVP acceptance criteria, non-goals, risks, and open choices.
- [Experience](product/experience.md) — city/tag entry, preference pages, polling states, image/place result, and accessibility.
- [Delivery plan](product/delivery-plan.md) — completed product milestones and remaining reliability/demo work.

## Architecture

- [Overview](architecture/overview.md) — runtime map and durable provider flow.
- [Domain model](architecture/domain-model.md) — current persistence, public projection, checkpoints, and invariants.
- [API contract](architecture/api-contract.md) — current operational, itinerary, and preference-learning endpoints.
- [External integrations](architecture/integrations.md) — Cala, OpenAI, fal, app-owned media, and failure rules.
- [Decision log](architecture/decisions/README.md) — accepted decisions, including city/tag input and preference learning before generation.

## Engineering

- [Local development](engineering/local-development.md) — Docker/host workflows, smoke behavior, URLs, and troubleshooting.
- [Configuration](engineering/configuration.md) — canonical environment inventory and ownership rules.
- [Quality](engineering/quality.md) — offline checks, composed smoke behavior, and required coverage.
- [Security](engineering/security.md) — current controls and safeguards required before public deployment.

## Status vocabulary

- **Current** — implemented and verified behavior that documentation must track.
- **Confirmed** — explicitly required product direction, even if its UI is not implemented.
- **Proposed** — intended behavior that may still change.
- **Open** — a decision is still required.

## Sources of truth

| Concern | Canonical source |
| --- | --- |
| Product boundaries | `docs/product/` |
| HTTP schemas | FastAPI OpenAPI at `/docs` |
| Persistent schema | SQLAlchemy models plus Alembic revisions |
| Durable decisions | `docs/architecture/decisions/` |
| Environment variables | `.env.example`, explained in configuration docs |
| Local commands | Root `Makefile`, explained in local-development docs |
