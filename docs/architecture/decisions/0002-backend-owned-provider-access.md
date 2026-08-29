# 0002: Backend-owned provider access

- Status: Accepted
- Date: 2026-08-29

## Context

The product depends on Cala, OpenAI, and fal. Their credentials are sensitive, protocols differ, and latency, quota, cost, validation, and failures require one controlled boundary. Direct browser calls would expose secrets and couple UI code to provider behavior.

## Decision

The Python backend boundary—FastAPI plus its generation worker—is the sole application gateway to Cala, OpenAI, and fal.

- Browser code communicates with application-owned Next.js/FastAPI routes.
- Provider credentials exist only in API/worker configuration.
- The worker performs current intent parsing, Cala query/search, OpenAI structured planning, fal submission/retrieval, and media copy.
- Each provider is wrapped by an application-owned adapter.
- Adapters normalize responses/errors before returning application concepts.
- Routes, persistence, and frontend do not depend on provider SDK classes or raw provider payloads.
- Provider status is redacted and makes no billable call.
- Long-running orchestration belongs to the worker; FastAPI request handlers do not wait for providers.

Thin same-origin Next.js proxy routes are allowed. They may forward application requests but may not become a second provider gateway.

## Consequences

- Secrets, cost controls, logging, timeouts, validation, retries, and error mapping have one enforcement boundary.
- Provider replacement and offline test doubles do not change the public contract.
- The backend bears orchestration complexity and must prevent prompt/provider data from leaking into public or log schemas.
- Provider-specific capability requires a deliberate application-domain addition, not an ad hoc frontend field.

## Alternatives considered

### Call providers from browser code

Rejected because it exposes credentials, complicates CORS, and couples the UI to provider protocols.

### Make Next.js server routes another provider backend

Rejected because it splits policy, errors, observability, checkpoints, and costs across two systems.

### Persist provider responses as the public result

Rejected because provider schema changes, unsafe fields, and provider replacement would leak through the application.
