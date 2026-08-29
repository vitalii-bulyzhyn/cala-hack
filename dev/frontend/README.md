# Travel Journal frontend

The Next.js application contains a frontend-only prototype of the illustrated
travel journal journey. It collects a destination, opens a review journal, then
shows a temporary creating state before opening the final static journal. This
trial does not call the backend or generate itinerary data yet.

## Run locally

From the repository root, use `make dev` for the complete Docker Compose stack.
To run only this app on the host:

```sh
nvm use
npm ci --prefix dev/frontend
npm --prefix dev/frontend run dev
```

The app is available at <http://localhost:3000>.

## Prototype flow

The current routes are:

- `/` — destination input, nine Season and Food & drink multi-select tags, and
  Start action.
- `/journal` — the fitted, unscrollable six-page Mantine Book journal. The first
  pass includes Like/Not for me controls; `stage=final` renders the final pass
  without them.
- `/creating` — a five-second UI-only transition between the review and final
  journal. Invalid direct visits return to the entry page.

Start opens the review journal directly. After page six, Create journal opens
the creating state, which replaces itself with a fresh final journal.

## Journal interaction trial

The canonical journal route is <http://localhost:3000/journal>. The original
standalone trial remains available at <http://localhost:3000/journal-demo>.
Both use Mantine Book with three physical sheets, six page faces, and one
repeated decorative SVG background. The copy and page labels remain live HTML
above the image. Review faces have local Like/Not for me controls; final faces
do not. The book scales from both available width and height so the complete
interaction stays inside an unscrollable viewport. Previous/Next buttons and
the keyboard's Left/Right arrow keys both move between page states.

This is an interaction spike, not the production itinerary journal. The
placeholder page art can be replaced at
`public/journal-demo/static-page.svg` without changing the page components.

## Configuration

`BACKEND_URL` is server-only and defaults to `http://localhost:8000`. Docker
Compose overrides it with `http://backend:8000`. The existing same-origin
`/api/backend-health` proxy is retained for future integration, but the current
prototype does not call it.

## Checks

```sh
npm --prefix dev/frontend run lint
npm --prefix dev/frontend run typecheck
npm --prefix dev/frontend run build
```

The `runner` Docker stage uses Next.js standalone output for production. The
development stage remains the default image for the repository's hot-reloading
Compose workflow; build production with `docker build --target runner`.
