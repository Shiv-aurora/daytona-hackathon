# ElevenLabs widget for the UI session (agent `agent_9901m52xtp8aenjb85rmkdxcyacr`, "Relay AI Helper")

```html
<script src="https://unpkg.com/@elevenlabs/convai-widget-embed" async type="text/javascript"></script>
<elevenlabs-convai agent-id="agent_9901m52xtp8aenjb85rmkdxcyacr"
  dynamic-variables='{"household_label":"Household A","request_category":"food","request_summary":"Water and food","org_name":"Harbor Relief","promised_when":"today at noon"}'></elevenlabs-convai>
```
Dynamic variables: `household_label`, `request_category`, `request_summary`, `org_name`, `promised_when`. All five must be
passed or the agent speaks the raw `{{...}}`. SDK alternative (`@elevenlabs/react`):
`useConversation().startSession({ agentId, dynamicVariables: { household_label: '...', ... } })` (the
`dynamic-variables` attribute is confirmed in the docs; `dynamicVariables` is confirmed for `@elevenlabs/client`
`Conversation.startSession`, assumed identical for the React hook, so verify against its types).

**Allowlist:** ElevenLabs dashboard > agent > Security. A public agent needs the allowlist to include `localhost` (and
`localhost:3000` if listed by origin) plus the Vercel hostname, e.g. `relay-demo.vercel.app`. With auth enabled, skip the
widget and fetch a signed URL from the API (`POST /runs/{run}/requests/{id}/voice-session` returns one).

**CSP / Permissions-Policy:** allow `script-src https://unpkg.com`, `connect-src https://api.elevenlabs.io wss://api.elevenlabs.io`,
`media-src blob:`, and `Permissions-Policy: microphone=(self)`. If the widget sits in an iframe, add `allow="microphone"`.

**What it can do:** talk (voice or text), ask the follow-up question, hang up via `end_call`, say the 911 line.
**What it cannot do:** update the dashboard. A browser widget has no server-bound session. Only the signed post-call
webhook `POST /webhooks/elevenlabs` (needs a public tunnel, `ELEVENLABS_WEBHOOK_SECRET`) reaches Relay, and for a
widget conversation it is recorded as unlinked (`GET /webhooks/elevenlabs/unlinked`, HTTP 202). No request is changed
and no request is guessed; a human reviews it. To resolve a request, use the `voice-session` route instead.

**Honest safety note:** with a built-in LLM, the emergency response is only a prompt rule, not our code-owned
`safety_check`. Only the Custom LLM bridge (`make agent-apply ARGS="--yes --custom-llm"`) puts code before the model.
Say so when demoing the widget. Check the live agent with `make agent-inspect`, text-test it with `make agent-simulate`.
