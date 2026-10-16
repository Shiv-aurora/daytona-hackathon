# ruff: noqa: F821
# Runs inside the sandbox. Summarizes verification state; it never resolves anything.
request = PAYLOAD['request']
received = [v['received'] for v in PAYLOAD['verifications']]
if request['status'] == 'resolved':
    state = 'already resolved by a recorded verification'
elif not received:
    state = 'no verification recorded yet; a human or consented call must verify'
else:
    state = 'latest verification: ' + str(received[-1])
print(json.dumps({'summary': f"Request {request['id']} is {request['status']}: {state}.",
                  'proposals': [{'type': 'needs_human_review', 'request_id': request['id']}]}))
