# ruff: noqa: F821
# Runs inside the sandbox. Scripted call rehearsal; no network, no model, fixed answer from payload.
request = PAYLOAD['request']
answer = PAYLOAD['scripted_answer']
if not PAYLOAD['call_opt_in']:
    print(json.dumps({'summary': 'No confirmed call opt-in; no call rehearsed.', 'proposals': []}))
else:
    replies = {'received': 'Yes, I received it.', 'not_received': 'No, I did not receive it.',
               'unsure': 'I am not sure.'}
    transcript = [
        {'speaker': 'agent', 'text': PAYLOAD['disclosure']},
        {'speaker': 'agent', 'text': f"Did you receive the {request['category']} delivery?"},
        {'speaker': 'survivor', 'text': replies[answer]},
    ]
    print(json.dumps({'summary': f'Rehearsed call; scripted answer: {answer}.', 'transcript': transcript,
                      'proposals': [{'type': 'queue_follow_up_call', 'request_id': request['id'],
                                     'rehearsal_answer': answer}]}))
