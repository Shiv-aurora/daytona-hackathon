"""Owner agent tool against a fake transport: no network, no key, no call."""
import importlib.util
import json
from pathlib import Path

from calls.agent_prompt import SYSTEM_PROMPT
from calls.elevenlabs import ElevenLabsClient
from calls.safety import disclosure

spec = importlib.util.spec_from_file_location(
    'elevenlabs_agent', Path(__file__).resolve().parents[1] / 'scripts/elevenlabs_agent.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

CB = '+1 555 010 0199'
GOOD = {'conversation_config': {'agent': {
    'first_message': disclosure('en', CB), 'disable_first_message_interruptions': True, 'language': 'en',
    'prompt': {'prompt': SYSTEM_PROMPT, 'llm': 'custom-llm', 'built_in_tools': {'end_call': {'name': 'end_call'}}}}},
    'platform_settings': {'auth': {'enable_auth': False, 'allowlist': [{'hostname': 'localhost'}]},
                          'overrides': {'conversation_config_override': {'agent': {'first_message': False,
                                        'language': False, 'prompt': {'prompt': False}}}},
                          'workspace_overrides': {'webhooks': {'post_call_webhook_id': 'wh1'}}}}
BAD = {'conversation_config': {'agent': {'first_message': 'Hi!', 'prompt': {'prompt': 'Be nice.', 'llm': 'gpt-4o'}}},
       'platform_settings': {'overrides': {'conversation_config_override': {'agent': {'first_message': True}}}}}


def fake(agent, sim=None, calls=None):
    def transport(method, url, headers, body, timeout):
        if calls is not None:
            calls.append((method, url, body))
        assert 'xi-api-key' in headers
        if url.endswith('/workspace/webhooks'):
            return 200, json.dumps({'webhooks': [{'webhook_id': 'wh1',
                                    'webhook_url': 'https://t.example/webhooks/elevenlabs?token=SECRET'}]}).encode()
        if url.endswith('/simulate-conversation'):
            return sim(json.loads(body)) if sim else (404, b'')
        if method == 'GET':
            return 200, json.dumps(agent).encode()
        return 200, b'{"secret_id":"s1"}'
    return lambda: ElevenLabsClient('k', 'a', transport)


def run(argv, factory, monkeypatch, capsys):
    monkeypatch.setenv('RELAY_CALLBACK_NUMBER', CB)
    monkeypatch.setenv('ELEVENLABS_AGENT_ID', 'agent_x')
    code = tool.main(argv, factory, lambda _: None)
    return code, capsys.readouterr().out


def test_inspect_good_agent_passes_and_hides_url_secret(monkeypatch, capsys):
    code, out = run(['inspect'], fake(GOOD), monkeypatch, capsys)
    assert code == 0 and 'FAIL  ' not in out and '0 FAIL' in out and 'SECRET' not in out
    assert 'https://t.example/webhooks/elevenlabs' in out


def test_inspect_bad_agent_fails_and_warns_builtin_llm(monkeypatch, capsys):
    code, out = run(['inspect'], fake(BAD), monkeypatch, capsys)
    assert code == 1 and 'FAIL  first message' in out and 'FAIL  end_call' in out
    assert 'FAIL  client overrides' in out and 'NOT code-owned' in out and 'FAIL  post-call webhook' in out


def test_apply_dry_run_changes_nothing_then_yes_patches_minimally(monkeypatch, capsys):
    calls = []
    code, out = run(['apply'], fake(BAD, calls=calls), monkeypatch, capsys)
    assert code == 0 and 'DRY RUN' in out and all(c[0] == 'GET' for c in calls)
    calls.clear()
    run(['apply', '--yes'], fake(BAD, calls=calls), monkeypatch, capsys)
    patch = json.loads(next(c[2] for c in calls if c[0] == 'PATCH'))
    agent = patch['conversation_config']['agent']
    assert agent['first_message'] == disclosure('en', CB) and agent['disable_first_message_interruptions'] is True
    assert agent['prompt']['prompt'] == SYSTEM_PROMPT and 'llm' not in agent['prompt']  # LLM untouched
    assert patch['platform_settings']['overrides']['conversation_config_override']['agent'] == {'first_message': False}


def test_apply_noop_when_already_correct(monkeypatch, capsys):
    calls = []
    code, out = run(['apply', '--yes'], fake(GOOD, calls=calls), monkeypatch, capsys)
    assert code == 0 and 'Nothing to change' in out and not any(c[0] == 'PATCH' for c in calls)


def responder(replies):
    def sim(body):
        first = body['simulation_specification']['simulated_user_config']['first_message']
        turns = [{'role': 'agent', 'message': disclosure('en', CB)}, {'role': 'user', 'message': first},
                 {'role': 'agent', 'message': replies(first)}]
        return 200, json.dumps({'simulated_conversation': turns}).encode()
    return sim


def good_reply(user):
    u = user.lower()
    if 'did not' in u:
        return 'So the food did not arrive. I am asking a person on the recovery team to follow up.'
    if 'arrived' in u:
        return 'So the food arrived. Thank you.'
    if 'fell' in u:
        return "Please hang up and call 911 now. I'm alerting a person on the recovery team."
    if 'medicine' in u:
        return "I can't give medical advice. Please ask a doctor or pharmacist."
    if 'real person' in u:
        return 'I am an automated assistant for the recovery team.'
    return "I can't promise that. I will ask a person on the team to follow up."


def test_simulate_all_pass(monkeypatch, capsys):
    code, out = run(['simulate'], fake(GOOD, responder(good_reply)), monkeypatch, capsys)
    assert code == 0 and out.count('PASS  ') == 6


def test_simulate_catches_unsafe_agent(monkeypatch, capsys):
    def unsafe(_):
        return 'Sure, I promise help will come. Take two aspirin. Where are you?'
    code, out = run(['simulate'], fake(GOOD, responder(unsafe)), monkeypatch, capsys)
    assert code == 1 and 'FAIL  c. emergency' in out and 'FAIL  f. asks for a promise' in out


def test_simulate_falls_back_when_endpoint_gone(monkeypatch, capsys):
    code, out = run(['simulate'], fake(GOOD), monkeypatch, capsys)
    assert code == 1 and 'test widget' in out and 'father fell' in out


def test_missing_key(monkeypatch, capsys):
    code, out = run(['inspect'], lambda: None, monkeypatch, capsys)
    assert code == 1 and 'ELEVENLABS_API_KEY' in out
