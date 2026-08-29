# Configuration

Status: Environment configuration, preference-learning seam, provider-backed generation, checkpoints, and app-owned local media are **Current**. Production values/storage remain **Open**.

`.env.example` is the canonical implemented-variable inventory. This document explains ownership and safety; update both in the same change.

## Application and local infrastructure

| Variable | Used by | Secret | Purpose/default |
| --- | --- | --- | --- |
| `APP_NAME` | Backend | No | FastAPI metadata; `Travel Journal API`. |
| `APP_ENV` | Backend | No | Runtime label; `development` locally. |
| `LOG_LEVEL` | Backend | No | Validated log verbosity. |
| `BACKEND_CORS_ORIGINS` | Backend | No | JSON/comma-separated browser origins; local frontend included. |
| `FRONTEND_PORT` | Compose | No | Host frontend port, `3000`. |
| `BACKEND_PORT` | Compose | No | Host backend port, `8000`. |
| `POSTGRES_PORT` | Compose | No | Host Postgres port, `5432`. |
| `REDIS_PORT` | Compose | No | Host Redis port, `6379`. |
| `PGADMIN_PORT` | Compose | No | Host pgAdmin port, `5050`. |
| `DATABASE_URL` | API/worker/migrate | Contains credentials | Postgres URL; localhost for host processes, Compose hostname in containers. |
| `REDIS_URL` | API/worker | May contain credentials | Optional readiness, run-ID wake-ups, and worker heartbeat; not canonical state. |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | API/worker | No | Redis connect bound, `2`. |
| `REDIS_OPERATION_TIMEOUT_SECONDS` | API/worker | No | Queue/heartbeat operation bound, `5`; blocking pop also includes poll duration. |
| `READINESS_TIMEOUT_SECONDS` | Backend | No | Per-dependency readiness bound, `2`. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Compose | Password secret | Local database/bootstrap values. |
| `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` | pgAdmin | Account/password | Local-only pgAdmin login. |
| `BACKEND_URL` | Next.js server | No; server-only | FastAPI origin for same-origin proxy; localhost on host and `backend:8000` in Compose. |
| `NEXT_PUBLIC_API_BASE_URL` | Browser | Public | Reserved/direct API base; never store secrets here. |

The API prefix is fixed at `/api/v1`; it is not an environment variable.

## Durable worker

| Variable | Default | Purpose |
| --- | --- | --- |
| `GENERATION_QUEUE_KEY` | `travel-journal:generation:queued` | Redis list of generation-run UUID wake-ups. |
| `GENERATION_MAX_ATTEMPTS` | `3` | Durable attempt limit, including checkpoint-resumed attempts. |
| `GENERATION_RETRY_BASE_SECONDS` | `5` | Base for exponential delayed retry. |
| `WORKER_NAME` | `generation-worker` | Lease-owner ID prefix. |
| `WORKER_POLL_SECONDS` | `2` | Redis pop timeout and HTTP `Retry-After`. |
| `WORKER_HEARTBEAT_KEY` | `travel-journal:generation:worker:heartbeat` | Base key; runtime hostname is appended. |
| `WORKER_HEARTBEAT_SECONDS` | `5` | Process heartbeat and Postgres lease-extension cadence. |
| `WORKER_HEARTBEAT_TTL_SECONDS` | `15` | Redis heartbeat expiry; must exceed cadence. |
| `WORKER_RECONCILE_SECONDS` | `5` | Independent scan interval for due Postgres work. |
| `WORKER_LEASE_SECONDS` | `60` | Claim lease; must exceed twice heartbeat cadence. |

API and worker share backend settings. Current Compose runs one sequential worker. Changing the Redis list key can strand hints but not durable runs; reconciliation still discovers them.

## Provider generation

| Variable | Secret | Purpose/default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | Required for a successful job; optional for boot. |
| `OPENAI_MODEL` | No | Replaceable default `gpt-5.6-terra`. |
| `OPENAI_TIMEOUT_SECONDS` | No | Responses call timeout, `120`. |
| `PROVIDER_CONTEXT_MAX_CHARS` | No | Maximum serialized Cala context passed to planning, `30000`. |
| `CALA_API_KEY` | Yes | Sent only as `X-API-KEY`; required for success. |
| `CALA_BASE_URL` | No | `https://api.cala.ai`. |
| `CALA_TIMEOUT_SECONDS` | No | Cala HTTP timeout, `30`. |
| `FAL_KEY` | Yes | fal queue credential; required for success. |
| `FAL_IMAGE_MODEL` | No | Replaceable default `fal-ai/flux/schnell`. |
| `FAL_START_TIMEOUT_SECONDS` | No | Queue submission/start bound, `30`. |
| `FAL_RESULT_TIMEOUT_SECONDS` | No | Result-wait bound per attempt, `180`. |

All three keys may be blank while booting. Initial preference pages and deterministic adaptive fallback still work from the bundled catalog. With `OPENAI_API_KEY`, adaptive ranking may use the configured OpenAI model. Once generation starts, missing any generation key ends it with `PROVIDER_CONFIGURATION_MISSING`.

Model IDs are configuration, not durable decisions. Prompt/schema versions and saved checkpoint schema belong in code and diagnostics.

## App-owned media

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEDIA_STORAGE_PATH` | `.data/generated-media` | Host-local root for copied generated images. Compose overrides to `/data/generated-media`. |
| `MEDIA_URL_PATH` | `/media` | FastAPI static mount and public URL prefix; cannot be `/`. |
| `MEDIA_DOWNLOAD_TIMEOUT_SECONDS` | `30` | Provider-image download bound. |
| `MEDIA_MAX_BYTES` | `15000000` | Maximum accepted image size in bytes. |

Compose mounts the same `generated_media` volume at `/data/generated-media` in API and worker. The worker writes an itinerary-scoped file atomically; the API serves it. This is demo storage, not a production object-store/CDN decision.

## Rules

- Commit only safe placeholders in `.env.example`; never commit `.env` or credentials.
- Provider, database, Redis, and pgAdmin secrets remain backend/server-side.
- Never print secrets, full DSNs, raw prompts/provider bodies, checkpoints, or authorization headers.
- `/api/v1/providers/status` reports configuration presence only—not values, quota, billing, or reachability.
- Live generation and configured `make smoke` can consume quota and money.
- Production must provide unique credentials, exact CORS/network rules, managed secret injection, rate/cost controls, and object storage.
- Restart affected processes after environment changes.

Provider semantics are in [External integrations](../architecture/integrations.md); setup is in [Local development](local-development.md).
