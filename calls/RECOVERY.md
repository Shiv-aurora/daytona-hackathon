# Recovery call adapter

`run_follow_up(job, context, transport)` returns the exact contract result. This
path asks about the specific request, not general wellbeing. Only an explicit
answer to the receipt question becomes true/false. Partial, conditional, unclear,
silent or provider-completed calls remain unverified. English answer recognition
is deliberately conservative; unsupported answers require human review.

`job` contains `call_id`, `request_id`, `run_id`, `disaster_id`. Context is resolved
on the server and contains scoped `request` and `survivor` records and a configured
`callback_number`. `call_opt_in` must be the boolean `True`.

The server supplies these hooks:

- `get_call_result(call_id)` returns a stored result or None.
- `claim_call(job)` atomically claims only queued jobs; false means never redial.
- `finish_call(job, result)` stores the result once. W2 applies receipt to storage.
- `emit_event(event)` writes each scoped system event once by its deterministic ID.
- `escalate(event)` persists immediate human escalation by deterministic ID.

Storage failures propagate. An unfinished attempt remains active for human review.
The server must not automatically reset it to queued. Hooks must use storage
transactions or a process lock for the single-process demo. The adapter's session
lock protects simultaneous turns, not cross-process job claims.

Transport has `dial(survivor_id)->bool`, `say(text)`, `listen()->str|None`, and
`hang_up()`. Tests use `calls.fakes.FakeTransport`. This is a clearly scripted demo;
it does not verify a real telephone call. Phone lookup belongs in a server-side
transport and must never appear in the returned results or operational events.

For ElevenLabs browser voice, call `open_follow_up(job, context)` once. If it
returns a RecoverySession, assign a server-generated opaque session ID to
`RecoveryVoiceBridge(secret).sessions[id]`. Set the configured ElevenLabs agent's
first message to `session.disclosure` unchanged, and send the session ID in
`elevenlabs_extra_body.relay_session_id` via the Custom LLM configuration. Use the
existing signed URL fetcher and SSE HTTP machinery. The first no-user completion
returns the receipt question. Typed fallback uses `session.hear(text)` through a
server-bound session; never accept a client-supplied claimed receipt result.

`handle_post_call(raw_body, signature, secret, lookup_session, now=None)` verifies
ElevenLabs HMAC plus timestamp then resolves only the provider conversation ID
using a server-owned mapping. Pass the raw request bytes and `ElevenLabs-Signature`
header. Unknown conversations fail closed. Duplicate completed events return the
existing result. Provider analysis and transcript yes/no are not proof of receipt;
only the live question/turn path can provide that evidence. An interrupted stream
remains unverified. Webhook emergency detection is a defensive fallback and cannot
replace live safety checks. Do not expose webhook HTTP until its secret and
conversation mapping exist.

Fresh ElevenLabs credentials, a configured Custom LLM agent, callback number,
public HTTPS callback, and confirmed recipient consent are still needed for live
voice. Outbound telephony is not enabled. No real calls or agent creation were
performed. Existing fixed disclosure/emergency templates are unchanged.

Official integration references:
[Post-call webhooks](https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks),
[HMAC reference implementation](https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/webhooks_custom.py).
