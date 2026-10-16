# Relay UI

Next.js + TypeScript + Tailwind. W4 owns this folder.

```bash
npm ci
npm run dev -- --hostname 127.0.0.1
npm run lint
npm test
npm run build
```

The existing `/console` is the offline baseline. W4 will replace it with the Response,
Organizations, Calls, and Intelligence workspace described in `../contracts/demo.md`.
The UI connects only to the backend API (`NEXT_PUBLIC_RELAY_API_URL`). It has no database driver,
service secrets, hosting project link, deployment hook, or deploy script. Direct database replay
has been retired; the recorded snapshot tests preserve the existing isolation coverage.
