# ruff: noqa: F821
# Runs inside the sandbox. PAYLOAD is prepended by the runner. Counts needs by category.
counts = {}
for r in PAYLOAD['requests']:
    counts[r['category']] = counts.get(r['category'], 0) + 1
print(json.dumps({'summary': f"{len(PAYLOAD['requests'])} requests across {len(counts)} categories",
                  'proposals': [{'type': 'category_counts', 'counts': counts}]}))
