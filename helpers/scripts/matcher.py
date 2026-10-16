# ruff: noqa: F821
# Runs inside the sandbox. Capability match only; a human confirms any claim.
request = PAYLOAD['request']
orgs = [o['id'] for o in PAYLOAD['organizations'] if request['category'] in o['capabilities']]
print(json.dumps({'summary': f"{len(orgs)} organizations list the {request['category']} capability",
                  'proposals': [{'type': 'organization_suggestion', 'request_id': request['id'],
                                 'organization_ids': sorted(orgs), 'requires_human_confirmation': True}]}))
