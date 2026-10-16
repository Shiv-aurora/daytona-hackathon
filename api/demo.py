"""No-network rehearsal: python -m api.demo --seed data/demo/seed.json."""
import argparse
import json

from api.demo_store import InMemoryRecoveryStore
from api.follow_up import execute_follow_up
from api.recovery import compare, queue_follow_up


class ScriptedTransport:
    """Synthetic recipient only; never makes a telephone call."""
    def __init__(self, answer):
        self.answer = answer

    def dial(self, _):
        return True

    def say(self, _):
        pass

    def listen(self):
        return self.answer

    def hang_up(self):
        pass


def main():
    parser = argparse.ArgumentParser(description='Relay synthetic backend rehearsal (no calls)')
    parser.add_argument('--seed', default='data/demo/seed.json')
    parser.add_argument('--store', choices=('memory', 'surreal'), default='memory')
    parser.add_argument('--run-id', default='demo-current')
    parser.add_argument('--request-id', default='current-supplies-1')
    parser.add_argument('--answer', default='no')
    args = parser.parse_args()
    with open(args.seed) as stream:
        seed = json.load(stream)
    if args.store == 'memory':
        store = InMemoryRecoveryStore(seed)
    else:
        from db.recovery import SurrealRecoveryStore
        store = SurrealRecoveryStore.from_env(seed=seed)
    try:
        call = queue_follow_up(store, args.run_id, args.request_id, {'idempotency_key': 'rehearsal-follow-up'})['call']
        result = execute_follow_up(store, args.run_id, call['id'], ScriptedTransport(args.answer), '+15555550100')
        evaluation = compare(store, args.run_id, {'idempotency_key': 'rehearsal-evaluation'})
        print(json.dumps({'mode': 'synthetic_no_network', 'call_result': result, **evaluation}, indent=2))
    finally:
        if hasattr(store, 'close'):
            store.close()


if __name__ == '__main__':
    main()
