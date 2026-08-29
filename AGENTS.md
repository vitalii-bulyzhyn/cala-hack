# Repository map

Travel Journal stores a destination city/tags, learns from visual activity choices, then creates a one-day plan, journal image, and linked place data. This file is only a navigation map; product and engineering decisions live under [`docs/`](docs/README.md).

## Where to look

| When changing | Read first | Code location |
| --- | --- | --- |
| Product behavior or scope | [`docs/product/`](docs/product/overview.md) | Both apps as needed |
| Journal experience and presentation | [`docs/product/experience.md`](docs/product/experience.md) | `dev/frontend/` |
| API, preference learning, domain data, or generation lifecycle | [`docs/architecture/`](docs/architecture/overview.md) and [ADR 0006](docs/architecture/decisions/0006-preference-learning-before-generation.md) | `dev/backend/` |
| Persistence, migrations, or background work | [`docs/architecture/domain-model.md`](docs/architecture/domain-model.md) and [ADR 0003](docs/architecture/decisions/0003-generation-lifecycle.md) | `dev/backend/app/db/`, `dev/backend/app/repositories/`, `dev/backend/app/worker/`, `dev/backend/migrations/` |
| OpenAI, Cala, fal, or media storage | [`docs/architecture/integrations.md`](docs/architecture/integrations.md), [ADR 0004](docs/architecture/decisions/0004-natural-request-and-journal-artifact.md), and [ADR 0005](docs/architecture/decisions/0005-city-and-tags-input.md) | `dev/backend/app/integrations/`, `dev/backend/app/services/` |
| Local setup or environment variables | [`docs/engineering/`](docs/engineering/local-development.md) | Root config and both apps |
| A durable technical tradeoff | [`docs/architecture/decisions/`](docs/architecture/decisions/README.md) | Add or supersede an ADR |

## Repository layout

```text
docs/                   Product, architecture, decisions, and engineering guides
dev/backend/            Python 3.12 / FastAPI API and worker code
dev/backend/app/worker/ Durable generation worker and Redis wake-up adapter
dev/backend/migrations/ Alembic migrations; runtime never creates schema
dev/frontend/           Next.js / TypeScript web app
infra/pgadmin/          Local pgAdmin server registration
compose.yaml            Full local stack, shared media volume, and infrastructure
Makefile                Canonical developer commands
.env.example            Complete, safe configuration template
```

## Invariants

- Applications live under `dev/`; shared infrastructure and documentation stay at the root.
- `/api/v1` is a fixed public prefix. The browser calls application-owned HTTP routes; provider credentials and calls stay in Python backend processes.
- Public itinerary status is only `pending`, `done`, or `fail`. A terminal response has `stage: null`; only `done` has a non-null, complete `result`.
- Creation starts in `learning_preferences` and must not create generation work. Preference completion creates the one orchestration run.
- Preference activities are immutable issued items; responses reference their itinerary/item IDs and are mutable only while learning is collecting.
- A `done` result requires destination/date/timezone metadata, three to five ordered places, typed links including a map link per place, and exactly one ready hero image.
- Postgres is the durable source of truth. Redis carries reconstructible generation-run UUID wake-ups only.
- Worker writes and checkpoints require a live Postgres lease and fencing version. Never bypass the generation-run repository.
- The saved application plan and saved fal request ID are immutable resume checkpoints. A retry must resume them instead of replanning or resubmitting.
- Generated provider media is copied into app-owned storage before success; the API serves the stored copy below `/media`.
- Database changes require a reviewed Alembic migration. Never edit an applied revision to represent a new schema.
- Provider payloads stop at adapter boundaries; application-owned schemas cross those boundaries.
- Never put a secret in `NEXT_PUBLIC_*` or return provider credentials/raw payloads.
- Update the relevant documentation or ADR with schema, configuration, or architectural changes.

Use [`docs/engineering/local-development.md`](docs/engineering/local-development.md) for commands. Run `make check`; run `make smoke` for composed runtime changes.
