# Local development

Status: Commands, six migrations, city-journal preference endpoints, worker pipeline, checkpoints, and shared local media are **Current**.

## Prerequisites

- Docker Desktop or another engine with Compose.
- Python 3.12 for host-local API/worker.
- Node.js 24 LTS and npm for host-local frontend.
- GNU Make.

## Docker-first start

```bash
make dev
```

This creates `.env` when missing, builds images, runs the one-shot `migrate` and local media-permission initialization, and starts frontend, backend, worker, Postgres, Redis, and pgAdmin. API and worker share the `generated_media` volume.

The stack starts with authoritative Barcelona, Toulouse, and Valencia journal-entry inventories, a paper journal asset, and optional empty provider keys. Initial/adaptive preference pages and a complete labeled demo journal work deterministically without keys or external calls. OpenAI may rerank adaptive choices when configured; the real Cala/OpenAI/fal generation path is selected only when all three keys exist.

Use `make setup` only for host-local application processes.

## Host-local workflow

```bash
make infra-up
make setup
make migrate
```

Then run separate terminals:

```bash
make backend-dev
make worker-dev
make frontend-dev
```

Host API/worker share `.data/generated-media` by default. `backend-dev` and `worker-dev` depend on migration.

## Commands

| Command | Purpose |
| --- | --- |
| `make dev` | Build/run one-shot migration and six long-running hot-reload services. |
| `make infra-up` | Start Postgres, Redis, and pgAdmin only. |
| `make infra-down` | Stop infrastructure without deleting volumes. |
| `make migrate` | Install backend dependencies and run `alembic upgrade head`. |
| `make backend-dev` | Migrate and run FastAPI with reload on host. |
| `make worker-dev` | Migrate and run the generation worker on host. |
| `make frontend-dev` | Run the npm/Next.js dev server on host. |
| `make logs` | Follow Compose logs. |
| `make check` | Offline backend/frontend/Compose validation. |
| `make smoke` | Build/wait for Compose and exercise creation, three preference pairs, responses, completion, worker, and terminal polling. |
| `make down` | Stop/remove stack without named-volume deletion. |
| `make reset` | **Destructive:** delete containers and project volumes, including generated media. |

## Local services

| Service | URL/port |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Backend | `http://localhost:8000` |
| FastAPI OpenAPI | `http://localhost:8000/docs` |
| Generated images | `http://localhost:8000/media/...` |
| Worker | Background process; no port |
| Migrate | One-shot `alembic upgrade head` |
| pgAdmin | `http://localhost:5050` |
| Postgres | `localhost:5432` |
| Redis | `localhost:6379` |

Example-only pgAdmin login is `admin@traveljournal.dev` / `admin`; database password is `travel_journal`.

## Smoke behavior

```bash
make smoke
```

The target:

1. Builds/starts Compose with health waits.
2. Checks API live/ready, frontend, same-origin health proxy, and pgAdmin.
3. Checks Postgres, Redis, hostname-scoped worker heartbeat/Postgres health, and `alembic check`.
4. Posts `{"city":"Barcelona","tags":["architecture","art","local food"]}` with an idempotency key.
5. Verifies compatible replay and incompatible-key conflict.
6. Reads the resource back in `learning_preferences` with the stored city/tags.
7. Retrieves/answers three initial pair pages and one adaptive single/pair page, verifies `204`, completes learning, and polls the created worker run to `done|fail`.

With empty keys smoke is non-billable and requires a complete offline demo result. With all real keys it can invoke OpenAI/Cala/fal, consume quota, and incur cost.

## Manual lifecycle

```bash
curl --fail -X POST http://localhost:8000/api/v1/itineraries \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: local-example-1' \
  -d '{"city":"Barcelona","tags":["art","local food","relaxed pace"]}'
```

Read the resource and request its first preference page:

```bash
curl --fail http://localhost:8000/api/v1/itineraries/RESOURCE_UUID
curl http://localhost:8000/api/v1/itineraries/RESOURCE_UUID/preference-pages/next
```

The second call returns the first pair. Submit each pair's complete decision map with `PUT .../preference-pages/{page_id}/feedback`, repeat for the three initial pages, optionally request/answer the adaptive page, then complete with `POST .../preference-learning/complete`. Poll its `status_url` and honor `Retry-After`.

## Dependency and storage behavior

- Postgres is required for readiness, accepted resources, claims, checkpoints, and results.
- Redis is optional in API readiness. Enqueue failure does not fail POST; reconciliation finds durable work independently.
- Provider availability/configuration is not readiness. Missing keys use offline demo generation by default.
- API and worker never create schema; Compose gates both on migration.
- fal source URLs are temporary inputs only. Success occurs after copying bytes into app storage.
- Normal down/up retains named database/Redis/pgAdmin/media volumes. `make reset` deletes them.
- `BACKEND_URL` is server-only. The current Next.js health proxy uses it; browser-visible API/media routing must preserve the backend origin contract.

## Troubleshooting

### Migration fails

Inspect `docker compose logs migrate`, Postgres health/credentials, and `make migrate`. Do not enable runtime table creation.

### Readiness returns `503`

Inspect Postgres and backend logs. Redis errors are optional/degraded and do not make API readiness fail.

### Redis is unavailable

Accepted work stays in Postgres and the worker can reconcile it, but worker Compose health and full smoke fail because the hostname-scoped heartbeat cannot be read.

### Resource stays `pending`

If stage is `learning_preferences`, finish the preference flow; no worker run exists yet. For later stages, check worker logs/health, migration head, Postgres connectivity, lease/retry state, and provider timeouts.

### Resource fails with `PROVIDER_CONFIGURATION_MISSING`

This occurs only when `OFFLINE_DEMO_ENABLED=false`. Set all three provider keys in `.env` or re-enable offline demo mode, restart API/worker, and create a new resource. Provider status reveals presence only. An existing terminal failure is not automatically re-opened.

### Provider-stage failure

Use public error code/request ID and sanitized worker logs. Retryable failures resume committed plan/fal checkpoints until the attempt limit. Do not inspect/log raw prompts or credentials.

### Image is missing or `/media` returns `404`

Confirm API and worker use the same `MEDIA_STORAGE_PATH`/Compose volume. Inspect media-copy errors and file ownership. A `done` response should never point directly to fal or lack the stored file.

### Worker is unhealthy

Run `docker compose exec -T worker python -m app.worker.healthcheck`. It requires Postgres and the heartbeat belonging to that container hostname.

### Frontend backend-health fails

Use `BACKEND_URL=http://localhost:8000` for a host frontend and `http://backend:8000` in Compose.

### Dependency install errors

Run `make setup`; use the backend virtual environment, Node 24 LTS, npm, and the committed lockfile.
