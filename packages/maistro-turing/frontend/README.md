# Turing frontend

Astro frontend for the Turing self-model surface. Talks to the Turing backend
(`packages/maistro-turing/backend`, default `http://localhost:8120`).

## Render split

- **SSG (static HTML)** — producer artifact pages (`/feed/[id]`). Built from an
  Astro content collection (`src/content/config.ts`) that fetches `GET /v1/feed`
  at **build time** and emits one static page per artifact. Producer content is
  static HTML, not client-fetched per view.
- **SSR / islands (live)** — dashboard (`/`), unified feed list (`/feed`), chat
  (`/chat`), and admin (`/admin`). These set `prerender = false` and hydrate
  React islands (`client:load`) that call the live API at request/interaction
  time.

## Theme — approximated, not vendored

The dark/minimal/terminal-cyberpunk aesthetic is **hand-written CSS**
(`src/styles/global.css`), not an installed theme package. It approximates the
visual language of the open-source **Null Trace** Astro theme (dark background,
monospace/terminal accents, minimal chrome) and blends in ideas from **Decker**
(card-based content layout), **Anglefient** (accent-line minimalism),
**Zaggonaut** (restrained type scale), plus standard AI-chat UI conventions
(message bubbles, streaming indicator, sidebar nav).

Why approximate rather than vendor: those theme packages aren't pinned
dependencies here and their exact sources weren't fetched, so reproducing the
visual ideas directly in CSS keeps the build self-contained and license-clean.
The CSS variables in `:root` are the single place to retune the palette.

## Dev

```bash
npm install
PUBLIC_TURING_API=http://localhost:8120 npm run dev   # http://localhost:4321
```

`PUBLIC_TURING_API` is the live API base used by the islands and the build-time
content loader. For SSG of artifact pages, the API must be reachable during
`npm run build` (set `TURING_BUILD_KEY` if the feed requires a bearer token).
