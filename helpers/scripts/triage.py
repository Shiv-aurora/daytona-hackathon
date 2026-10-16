# ruff: noqa: F821
# Runs inside the sandbox. Orders work by deadline then status only; it never ranks people.
order = {'reopened': 0, 'open': 1, 'claimed': 2, 'awaiting_verification': 3}
rows = [r for r in PAYLOAD['requests'] if r['status'] in order]
rows.sort(key=lambda r: (r.get('due_at') is None, r.get('due_at') or '', order[r['status']], r['id']))
print(json.dumps({'summary': f'{len(rows)} unresolved requests ordered by deadline and status',
                  'proposals': [{'type': 'work_order', 'request_ids': [r['id'] for r in rows]}]}))
