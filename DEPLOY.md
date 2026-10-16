# Deploy the Relay demo to Vercel

The deployed app runs fully in the browser (simulated backend). No Python API, SurrealDB, or env vars are needed.

## Dashboard
1. vercel.com -> Add New -> Project -> Import the GitHub repo `Shiv-aurora/daytona-hackathon`.
2. Set **Root Directory** to `ui` (Edit -> select `ui`).
3. Framework Preset: **Next.js** (auto-detected). Leave build/install commands as default.
4. Environment Variables: none.
5. Click **Deploy**.

## CLI
```
npx vercel login
npx vercel --cwd ui          # preview deploy (answer prompts; framework Next.js)
npx vercel --cwd ui --prod   # production deploy
```

## Later: connect a real backend
Project -> Settings -> Environment Variables -> add `NEXT_PUBLIC_RELAY_API_URL` (public https URL of the Relay API,
which must allow CORS from your Vercel domain). Redeploy. Blank means the simulated backend.

## ElevenLabs widget
In the ElevenLabs agent settings -> Security, add your Vercel domain (e.g. `your-app.vercel.app`, plus any custom domain)
to the allowlist. The site already sends `Permissions-Policy: microphone=(self)`.

## Post-deploy smoke checklist
- [ ] `/` redirects to `/live`; `/live`, `/response`, `/calls`, `/organizations`, `/intelligence` all load (200).
- [ ] On `/live`, click **Start demo**: the flow runs to completion with no errors in the browser console.
- [ ] Run the **Safety demo** (emergency escalation) and confirm it escalates to a human.
- [ ] Mode shows Simulated; no requests go to localhost.
- [ ] `/api/replay/runs` returns 503 "not configured" (expected); legacy `/console` and `/call/x` render without crashing.

Notes: legacy replay routes read no files and need no database; they respond 503 by design.
