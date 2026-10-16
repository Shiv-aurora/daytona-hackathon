# Live ElevenLabs setup (owner steps)

1. Fill `.env` (copy `.env.example`): `ELEVENLABS_API_KEY`, `RELAY_CALLBACK_NUMBER` (a number you own), `RELAY_LLM_SECRET` (any long random string).
2. Create the agent: `NGROK_DOMAIN=<your-tunnel-host> RELAY_ENV_FILE=.env python -m calls.voice.setup_agent`; put the printed id in `ELEVENLABS_AGENT_ID`. Verify with `--check`.
   It uses a Custom LLM at `https://<tunnel>/v1`, so every survivor turn passes the code-owned emergency check before any model.
3. Start the API: `make serve` (port 8787), then a public tunnel: `ngrok http 8787` (or cloudflared). Use its https host as `NGROK_DOMAIN`.
4. ElevenLabs dashboard > Agents > Settings > Webhooks: post-call transcription URL `https://<tunnel>/webhooks/elevenlabs`; copy the signing secret to `ELEVENLABS_WEBHOOK_SECRET`.
5. Check: `make check-elevenlabs` (add `STT=sample.wav` to test Scribe). It places no call.
6. Demo: dashboard POSTs `/runs/{run}/requests/{id}/voice-session`, connects with the returned `signed_url` and passes `custom_llm_extra_body` (the opaque session id) when starting the conversation.
7. Intake STT: `POST /runs/{run}/intake/transcribe` (multipart `file`, or JSON `audio_base64`). With a blank key it returns `provider:"fake"`.

Limits: sessions live in API process memory (restart drops them; a webhook for an unknown conversation answers 404 and a human reviews the active call).
Needs the signed-URL response to include `conversation_id`; the checker warns if not. Only explicit yes/no answers verify; unclear, silent or contradictory ones stay open.
Real survivors need confirmed opt-in; synthetic seed opt-in does not authorize calling a real person. No outbound telephony. Scribe upload cap 25 MB.
