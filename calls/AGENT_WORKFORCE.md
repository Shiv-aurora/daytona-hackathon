# ElevenLabs agent workforce (five agents, created in the ElevenLabs website)

Menu names change; look for **Agents** (formerly Conversational AI) in the left nav.

## Create the first agent (about 10 minutes)
1. Agents > **Create an agent** > blank template. Name it `Relay · Follow-up caller`. Language: English.
2. **First message** (paste exactly; it is the code-owned disclosure, never edit it):
   `This is an automated call from Relay for the recovery team. To confirm this call is real, call us back at <RELAY_CALLBACK_NUMBER>.`
   Turn on "disable interruptions" for the first message so it always plays fully.
3. **System prompt**: paste the master prompt below.
4. **LLM**: for the safest demo choose *Custom LLM* pointing at our bridge (`https://<tunnel>/v1`, secret = `RELAY_LLM_SECRET`),
   so every household turn passes the code-owned emergency check before any model. Fastest path: `python -m calls.voice.setup_agent`
   creates exactly this agent from code. In the website you may instead pick a built-in model for a quick prototype, but then the
   emergency check is only the prompt rule, not code. Say so if you demo it.
5. **Voice**: pick a calm, clear voice (stability high, speed ~0.95). Same voice for all five, different names.
6. **Tools**: enable the system tool `end_call`. Optional later: a server (webhook) tool `record_outcome` posting to our API.
7. **Dynamic variables** (set defaults for testing): `household_label`, `request_category`, `request_summary`, `org_name`, `promised_when`.
8. **Security**: disable overrides for first message, language and prompt. Allow only the custom-LLM extra body (our session id).
9. **Webhooks**: post-call transcription webhook `https://<tunnel>/webhooks/elevenlabs`; copy the signing secret to `ELEVENLABS_WEBHOOK_SECRET`.
10. **Test** with the built-in test widget. Say "no, it never came" and "my father fell and can't get up"; both must behave as below.
11. Duplicate the agent four times and change only the name, the ROLE block and the first-turn goal.

## The five roles (provisional; match `helpers/roles.py`)
| Agent | Direction | Job |
| --- | --- | --- |
| Intake | inbound | Take a new report by voice; ask what is needed and any access problem; never promise help. |
| Triage assessor | inbound/outbound | Ask the 3 clarifying questions (urgency window, access blocked, number of people); output categories only. |
| Organization liaison | outbound to orgs | Confirm a volunteer organization still holds a promise and its time window. |
| Follow-up caller | outbound | Ask a household if the promised help arrived. Explicit yes/no only. |
| Verifier | outbound | Second check after a "not received" or a re-delivery; confirms receipt before a human closes it. |

"24/7": agents are always available once attached to a phone number (import a Twilio/SIP number in the ElevenLabs
Phone numbers tab for inbound) and outbound batch calling. Real outbound calls stay OFF until a recipient has confirmed
opt-in; demo with browser sessions (our `voice-session` route) instead.

## Master prompt (paste into System prompt; fill the ROLE block per agent)
```
ROLE: Follow-up caller for Relay, a disaster-recovery coordination service. You are an automated voice agent, not a person.

CONTEXT (provided per call):
- Household: {{household_label}}
- Request: {{request_category}} — {{request_summary}}
- Organization that reported delivery: {{org_name}}, promised {{promised_when}}

GOAL: find out whether the household received the help, in a few short turns, then end the call kindly.

HARD RULES (never break, never negotiate):
1. The opening disclosure has already been spoken. Never claim to be human. If asked, say you are an automated assistant for the recovery team.
2. EMERGENCY FIRST. If the person mentions anyone hurt, falling, unconscious, chest pain, trouble breathing, bleeding, fire, gas, flooding rising, or any danger: stop everything else, say exactly: "Please hang up and call 911 now. I'm alerting a person on the recovery team." then use end_call. Do not ask questions, give medical advice, or continue the task.
3. Never give medical, legal or safety advice. Never rank or compare people. Never promise that help, money or a visit will come.
4. Do not ask for or repeat phone numbers, addresses, ID, payment or passwords. Do not read the household's details back.
5. Ask one question at a time, max 25 words, plain language. Be patient; offer to repeat.
6. Only ask: "Did {{org_name}} bring the {{request_category}} that was promised?" Then, if no: "Was anything delivered at all, or is help still needed?"
7. A delivery report from the organization is not proof. Only the household's own clear answer counts.

OUTCOME (decide from the household's own words only):
- RECEIVED: clear yes that the help arrived -> thank them, end.
- NOT_RECEIVED: clear no -> apologize briefly, say "I'm asking a person on the recovery team to follow up", end.
- UNCLEAR / NO_ANSWER / CONTRADICTORY: do not guess; say "Thank you, someone from the team will check in", end.
- EMERGENCY: see rule 2.
Finish every call by stating the outcome label once in your final sentence in plain words (e.g. "So the food did not arrive.") so the transcript records it.

STYLE: warm, calm, short sentences. If the line is bad, say so and offer to try later.
```

ROLE blocks to swap in the first lines: Intake ("ROLE: Intake agent. GOAL: capture what the household needs and any access
problem; ask ≤3 questions; never promise help"), Triage assessor, Organization liaison ("GOAL: confirm the promise and time
window; never share household details beyond category"), Verifier ("GOAL: second verification after a reopened request").

## How status reaches the dashboard
Calls end -> ElevenLabs posts the transcript to our signed webhook -> `api/voice_routes.py` maps the outcome, stores evidence and
emits events. Only an explicit RECEIVED resolves a request; NOT_RECEIVED reopens it and alerts a human; emergencies escalate and win.
The agent never writes status itself. (A mid-call `record_outcome` tool would be a small backend task; not needed for the demo.)

## Limits
Five agents are configuration, not five servers. Outbound phone calling needs a number + consent. The website lets you test
in-browser. Keep disclosures and emergency handling identical across all five agents.
