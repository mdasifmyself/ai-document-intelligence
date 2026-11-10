# DocIntel web app

Next.js 16 (React 19, TypeScript). Deployed on Vercel. Every API call goes to `/api/*` on the same origin, and
`next.config.ts` forwards it to `BACKEND_ORIGIN`.

```bash
cp .env.example .env.local     # BACKEND_ORIGIN=http://localhost:8000
npm install
npm run dev                    # http://localhost:3000
npm run build                  # production build (CI runs tsc + build)
```

Pages: `/` (overview), `/dashboard`, `/upload`, `/documents`, `/documents/[id]`, `/review`, `/search`,
`/cross-checks`, `/system`, `/guide`, `/how-it-works`. Shared code: `lib/api.ts` (requests with automatic retry and
plain-language errors), `lib/labels.ts` (every status, problem and "What to do" text), `components/`.

Typography: Manrope (headings, interface) and Helvetica Neue (reading text, Arial fallback).
