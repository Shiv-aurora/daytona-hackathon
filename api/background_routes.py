"""Read-only real NYC 311 background (Hurricane Ida, Queens, 2021). No households, no contact fields."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

LABEL = "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."
SOURCE = Path(__file__).resolve().parents[1] / 'data/scenarios/s1/events.jsonl'
FIELDS = ('key', 'reported_at', 'agency', 'text', 'street', 'zip', 'lat', 'lng')


def _from_file():
    seen, out = set(), []
    for line in SOURCE.read_text().splitlines():
        e = json.loads(line)
        if e.get('origin') != 'real' or not e.get('real_311_key') or e['real_311_key'] in seen:
            continue
        seen.add(e['real_311_key'])
        geo = e.get('geo') or {}
        out.append({'key': str(e['real_311_key']), 'reported_at': e['ts_real'],
                    'agency': (e.get('channel_meta') or {}).get('author'), 'text': e['text'],
                    'street': e.get('address_raw'), 'zip': None, 'lat': geo.get('lat'), 'lng': geo.get('lng')})
    return out


def handle(store, path):
    query = parse_qs(urlsplit(path).query)
    limit = max(1, min(int(query.get('limit', ['500'])[0]), 2000))
    reader = getattr(store, 'list_background_311', None)
    rows = reader(limit) if reader else _from_file()[:limit]
    source = 'surrealdb' if reader else 'scenario file'
    return 200, {'label': LABEL, 'source': source, 'count': len(rows),
                 'rows': [{k: r.get(k) for k in FIELDS} for r in rows]}
