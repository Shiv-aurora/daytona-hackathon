from api import background_routes
from api.demo_store import InMemoryRecoveryStore


def test_background_311_is_real_only_and_has_no_contact_fields():
    status, body = background_routes.handle(InMemoryRecoveryStore.__new__(InMemoryRecoveryStore), '/background-311?limit=50')
    assert status == 200 and body['source'] == 'scenario file' and body['count'] == 50
    assert 'real NYC Open Data' in body['label']
    for row in body['rows']:
        assert set(row) == set(background_routes.FIELDS)
        assert row['key'] and row['lat'] is not None
    keys = [r['key'] for r in body['rows']]
    assert len(keys) == len(set(keys))


def test_limit_is_clamped():
    _, body = background_routes.handle(object(), '/background-311?limit=999999')
    assert body['count'] <= 2000
