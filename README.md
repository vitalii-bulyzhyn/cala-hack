# Travel Journal

Travel Journal turns a destination city, traveler-selected tags, and a short visual preference-learning flow into a grounded one-day itinerary and hand-drawn journal image. The backend stores every displayed activity and like/dislike response before it starts Cala/OpenAI/fal generation.

`POST /api/v1/itineraries` returns the durable ID in stage `learning_preferences`. Preference page/response/completion APIs collect the six initial answers plus an answered adaptive page; only completion creates the worker run. Public status remains `pending`, `done`, or `fail`.

## Start the stack

The Docker workflow requires Docker with Compose. Host-local app development uses Node.js 24 LTS, npm, and Python 3.12.

```bash
make dev
```

This creates a safe `.env` when missing, runs the one-shot migration service, and starts six long-running services. `make setup` prepares host-local dependencies instead.

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:3000> |
| Backend API | <http://localhost:8000> |
| FastAPI docs | <http://localhost:8000/docs> |
| Generated media | <http://localhost:8000/media/> |
| Generation worker | Background service; no host port |
| pgAdmin | <http://localhost:5050> |
| Postgres | `localhost:5432` |
| Redis | `localhost:6379` |

The stack boots without provider credentials. Preference pages use the bundled activity catalog and deterministic ranking; an OpenAI key optionally improves adaptive ranking. After learning completes, missing generation credentials produce `PROVIDER_CONFIGURATION_MISSING`. Real provider calls can consume quota and incur cost.

Generated fal output is copied into app-owned local storage shared by the worker and API, then served below `/media`. This is suitable for local development and the hackathon demo; production object storage remains an explicit follow-up.

For host-local development, use `make migrate`, `make backend-dev`, `make worker-dev`, and `make frontend-dev`. Run `make check` for offline repository checks and `make smoke` for the composed lifecycle.

The example-only pgAdmin login is `admin@traveljournal.dev` / `admin`; the pre-registered local database password is `travel_journal`.

See [`AGENTS.md`](AGENTS.md) for the repository map and [`docs/README.md`](docs/README.md) for the documentation index.
