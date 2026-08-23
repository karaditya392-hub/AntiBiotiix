# AntiBioTix frontend

React + Vite + TypeScript. Replaces the previous vanilla `frontend/` **as a build
target only** — the FastAPI backend is unchanged.

## How this fits the backend

`backend/app.py` mounts `frontend/` at `/static` and serves `frontend/index.html`
at `/`. Vite therefore builds into `../frontend` with `base: "/static/"`, so the
emitted bundle is served by the routes that already existed. **No backend file was
modified for this migration.**

Routing is hash-based (`/#/review`) because the backend has no SPA catch-all and
adding one would have meant changing the backend.

## The console is the original application

`src/legacy/app.js` is the original `frontend/js/app.js`. It differs from it in
**four lines**, all decorative icon glyphs replaced to satisfy the no-emoji rule.
Every API call, payload, identifier, response parse, state transition and error
path is byte-identical.

`src/legacy/console.html` is the original `index.html` body with only Manus's
presentational substitutions applied. It is generated, not hand-written:

```bash
python scripts/build_console_markup.py
```

That script re-derives the markup from `frontend-legacy/index.html` and asserts
that all 62 element ids `app.js` queries survive. Run it if the console markup
ever needs to change, rather than editing the HTML by hand.

`src/pages/Console.tsx` injects that markup, then imports `app.js` and dispatches
`DOMContentLoaded` so the original boot sequence runs unmodified.

## Commands

```bash
npm install
npm run build      # -> ../frontend, which the backend serves
npm run dev        # Vite dev server on :5173, proxying /api to :8000
npm run typecheck
```

## Pending assets

Two Manus textures were not in the handoff. See `public/textures/README.md`.
