"""Create (or check) the ElevenLabs agent whose first message is Relay's code-owned disclosure.

    RELAY_ENV_FILE=.env python -m calls.voice.setup_agent          # create
    RELAY_ENV_FILE=.env python -m calls.voice.setup_agent --check  # verify only
    RELAY_ENV_FILE=.env python -m calls.voice.setup_agent --update # fix in place + verify
    add --language zh for the Mandarin agent (stored as ELEVENLABS_AGENT_ID_ZH)

The agent uses a Custom LLM (our bridge at https://$NGROK_DOMAIN/v1) authenticated with
RELAY_LLM_SECRET, has the end_call system tool, and does not allow client overrides, so the
browser cannot replace the disclosure. Prints the agent id to store as ELEVENLABS_AGENT_ID.
Configure this project's own credentials first; do not reuse the original project's env file.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from calls.safety import disclosure
from calls.voice.server import ELEVENLABS_API, load_env_file

MODEL_ID = "relay-call-agent"
AGENT_NAME = "Relay follow-up caller"
MULTILINGUAL_TTS = "eleven_flash_v2_5"  # non-English agents need a multilingual voice model


def agent_env_var(language: str) -> str:
    """Where each language's agent id lives: ELEVENLABS_AGENT_ID (en), ELEVENLABS_AGENT_ID_ZH, ..."""
    return "ELEVENLABS_AGENT_ID" if language == "en" else f"ELEVENLABS_AGENT_ID_{language.upper()}"


def agent_config(callback_number: str, domain: str, secret_id: str, language: str = "en") -> dict:
    config = {
        "name": AGENT_NAME if language == "en" else f"{AGENT_NAME} ({language})",
        "conversation_config": {
            "agent": {
                "first_message": disclosure(language, callback_number),
                "disable_first_message_interruptions": True,  # the disclosure always plays in full
                "language": language,
                "prompt": {
                    "prompt": "Relay storm-recovery follow-up call. Every reply comes from the Relay bridge.",
                    "llm": "custom-llm",
                    "custom_llm": {"url": f"https://{domain}/v1", "model_id": MODEL_ID,
                                   "api_key": {"secret_id": secret_id}},
                    "built_in_tools": {"end_call": END_CALL_TOOL},
                },
            },
        },
        "platform_settings": PLATFORM_SETTINGS,
    }
    if language != "en":
        config["conversation_config"]["tts"] = {"model_id": MULTILINGUAL_TTS}
    return config


# The final line before hang-up (e.g. the 911 line) cannot be talked over.
END_CALL_TOOL = {"name": "end_call", "description": "End the call.", "disable_interruptions": True,
                 "params": {"system_tool_type": "end_call"}}

# The browser may send only our session id (custom LLM extra body); it can never replace the
# disclosure, language or prompt.
PLATFORM_SETTINGS = {"overrides": {
    "custom_llm_extra_body": True,
    "conversation_config_override": {
        "agent": {"first_message": False, "language": False, "prompt": {"prompt": False}}}}}


def problems(config: dict, callback_number: str, language: str = "en") -> list[str]:
    """Why a fetched agent config is not safe to call with (empty list means OK)."""
    agent = config.get("conversation_config", {}).get("agent", {})
    found = []
    if agent.get("first_message") != disclosure(language, callback_number):
        found.append("first_message is not the code-owned disclosure")
    if agent.get("language", "en") != language:
        found.append(f"agent language is not {language}")
    if agent.get("disable_first_message_interruptions") is not True:
        found.append("the disclosure can be interrupted before it finishes")
    if agent.get("prompt", {}).get("llm") != "custom-llm":
        found.append("replies would come from ElevenLabs' model, skipping the safety check")
    overrides = config.get("platform_settings", {}).get("overrides", {})
    if overrides.get("conversation_config_override", {}).get("agent", {}).get("first_message"):
        found.append("clients may override the first message")
    if not overrides.get("custom_llm_extra_body"):
        found.append("custom_llm_extra_body override is disabled, so the browser session id cannot reach the bridge")
    return found


def _call(method: str, path: str, api_key: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(f"{ELEVENLABS_API}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"xi-api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    load_env_file(os.environ.get("RELAY_ENV_FILE"))
    api_key, callback = os.environ["ELEVENLABS_API_KEY"], os.environ["RELAY_CALLBACK_NUMBER"]
    language = sys.argv[sys.argv.index("--language") + 1] if "--language" in sys.argv else "en"
    if "--update" in sys.argv:  # fix an existing agent in place (keeps its LLM secret)
        agent_id = os.environ[agent_env_var(language)]
        _call("PATCH", f"/convai/agents/{agent_id}", api_key, {
            "conversation_config": {"agent": {"first_message": disclosure(language, callback),
                                              "disable_first_message_interruptions": True,
                                              "prompt": {"built_in_tools": {"end_call": END_CALL_TOOL}}}},
            "platform_settings": PLATFORM_SETTINGS})
        sys.argv.append("--check")
    if "--check" in sys.argv:
        found = problems(_call("GET", f"/convai/agents/{os.environ[agent_env_var(language)]}", api_key),
                         callback, language)
        print("agent OK" if not found else "agent NOT safe: " + "; ".join(found))
        return 1 if found else 0
    secret = _call("POST", "/convai/secrets", api_key,
                   {"type": "new", "name": f"relay-llm-secret-{language}", "value": os.environ["RELAY_LLM_SECRET"]})
    created = _call("POST", "/convai/agents/create", api_key,
                    agent_config(callback, os.environ["NGROK_DOMAIN"], secret["secret_id"], language))
    print(f"{agent_env_var(language)}={created['agent_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
