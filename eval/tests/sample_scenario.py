"""Small fictional scenario with hand-worked scores. Streets and 555-01xx numbers are made up.

Times are simulated hours since day 0. AS_OF is day 10 (hour 240), so the promise probes run at
hours 72, 144 and 216. The comments give the arithmetic behind the values in test_scorer.py.
"""

from schemas import SCENARIO_RUN_ID

SCENARIO = "scn-sample"
RELAY = "run-relay-1"
BASELINE = "run-baseline-1"
AS_OF = 240.0

REGISTRY = [
    {"household_id": "hh-oakes", "address": "14 Marigold Lane", "phone": "555-0101", "opt_in": True},
    {"household_id": "hh-vance", "address": "9 Quillfeather Ave", "phone": "555-0102", "opt_in": False},
    {"household_id": "hh-ruiz", "address": "3 Tinderbox Court", "phone": "555-0103", "opt_in": True},
    {"household_id": "hh-pell", "address": "22 Lanternwick St", "phone": "555-0104", "opt_in": True},
]

NEEDLES = [
    # Son promised to bring insulin by day 3 (ev-101) and never came.
    {"needle_id": "needle-oakes", "kind": "broken_promise", "household_id": "hh-oakes",
     "required_event_ids": ["ev-101", "ev-102", "ev-103"], "deadline": 120.0,
     "danger_at": 168.0, "response_hours": 12.0, "people_at_risk": 2},
    # Outage report, home-oxygen registry entry and an unanswered welfare check, across services.
    {"needle_id": "needle-vance", "kind": "cross_service_join", "household_id": "hh-vance",
     "required_event_ids": ["ev-201", "ev-202", "ev-203"], "deadline": 150.0,
     "danger_at": 200.0, "response_hours": 24.0, "people_at_risk": 3},
    # Opted-in resident stopped answering check-ins.
    {"needle_id": "needle-ruiz", "kind": "silent_household", "household_id": "hh-ruiz",
     "required_event_ids": ["ev-301", "ev-302"], "deadline": 200.0,
     "danger_at": 210.0, "response_hours": 24.0, "people_at_risk": 1},
]

# "No power" at hh-pell on day 2 (ev-401), restored the next day (ev-402). Alarming but resolved.
DECOYS = [{"decoy_id": "decoy-pell-outage", "household_id": "hh-pell", "event_ids": ["ev-401", "ev-402"]}]

# Due by AS_OF: pr-2, pr-3, pr-5, pr-6. Open at each probe (made <= t < due, not yet kept):
#   h72:  pr-1 (2.17d old), pr-2 (2d), pr-3 (1.75d), pr-4 (0.92d)
#   h144: pr-1 (5.17d), pr-4 (3.92d)
#   h216: pr-1 (8.17d), pr-7 (0.67d)
PROMISES = [
    {"_id": "pr-1", "household_id": "hh-vance", "source_event_id": "ev-601", "made_ts": 20.0, "due_ts": 380.0},
    {"_id": "pr-2", "household_id": "hh-oakes", "source_event_id": "ev-101", "made_ts": 24.0, "due_ts": 80.0},
    {"_id": "pr-3", "household_id": "hh-ruiz", "source_event_id": "ev-501", "made_ts": 30.0, "due_ts": 90.0,
     "status": "kept", "status_ts": 80.0},
    {"_id": "pr-4", "household_id": "hh-pell", "source_event_id": "ev-602", "made_ts": 50.0, "due_ts": 400.0,
     "status": "kept", "status_ts": 150.0},
    {"_id": "pr-5", "household_id": "hh-pell", "source_event_id": "ev-403", "made_ts": 76.0, "due_ts": 100.0},
    {"_id": "pr-6", "household_id": "hh-ruiz", "source_event_id": "ev-502", "made_ts": 110.0, "due_ts": 130.0},
    {"_id": "pr-7", "household_id": "hh-vance", "source_event_id": "ev-503", "made_ts": 200.0, "due_ts": 260.0},
]

PROPOSALS = [
    # Catches needle-oakes: 96 < 120, cites 2 of 3. Reached: 96 + 12 < 168. Warning (168-96)/24 = 3.0.
    # It cites pr-2's source event too, but pr-2 fell due at 80, so it is not on time.
    {"_id": "p-1", "run_id": RELAY, "household_id": "hh-oakes", "ts": 96.0,
     "cited_event_ids": ["ev-101", "ev-103"]},
    # needle-vance is missed: p-2 cites only one required event, p-3 comes after the deadline.
    {"_id": "p-2", "run_id": RELAY, "household_id": "hh-vance", "ts": 100.0, "cited_event_ids": ["ev-201"]},
    {"_id": "p-3", "run_id": RELAY, "household_id": "hh-vance", "ts": 160.0,
     "cited_event_ids": ["ev-201", "ev-202"]},
    # Catches needle-ruiz: 192 < 200. Too late to reach: 192 + 24 = 216 >= 210. Warning 18/24 = 0.75.
    {"_id": "p-4", "run_id": RELAY, "household_id": "hh-ruiz", "ts": 192.0,
     "cited_event_ids": ["ev-301", "ev-302", "ev-999"]},
    # False escalation: cites the resolved outage.
    {"_id": "p-5", "run_id": RELAY, "household_id": "hh-pell", "ts": 60.0, "cited_event_ids": ["ev-401"]},
    # Escalates pr-5 on time: cites its source event, 85 < 100.
    {"_id": "p-6", "run_id": RELAY, "household_id": "hh-pell", "ts": 85.0, "cited_event_ids": ["ev-403"]},
    # Baseline run. Each of these would change a Relay number if it leaked across runs.
    {"_id": "b-1", "run_id": BASELINE, "household_id": "hh-vance", "ts": 110.0,
     "cited_event_ids": ["ev-201", "ev-202", "ev-203"]},
    {"_id": "b-2", "run_id": BASELINE, "household_id": "hh-oakes", "ts": 60.0, "cited_event_ids": ["ev-101"]},
    # Before pr-5's due time but does not cite ev-403, so it does not make pr-5 on time.
    {"_id": "b-3", "run_id": BASELINE, "household_id": "hh-pell", "ts": 75.0, "cited_event_ids": ["ev-402"]},
    # Proposals are run output: one stamped "scenario" or with no run_id counts for no run.
    {"_id": "s-1", "run_id": SCENARIO_RUN_ID, "household_id": "hh-pell", "ts": 70.0,
     "cited_event_ids": ["ev-402"]},
    {"_id": "p-orphan", "household_id": "hh-vance", "ts": 100.0, "cited_event_ids": ["ev-201", "ev-202"]},
]

CONTACTS = [
    {"_id": "c-1", "run_id": RELAY, "scenario_id": SCENARIO, "household_id": "hh-oakes", "ts": 200.0},
    {"_id": "c-2", "run_id": RELAY, "scenario_id": SCENARIO, "household_id": "hh-ruiz", "ts": 120.0},
    # Last time the Relay run heard from hh-ruiz: 90h before AS_OF, so silent.
    {"_id": "c-3", "run_id": RELAY, "scenario_id": SCENARIO, "household_id": "hh-ruiz", "ts": 150.0},
    {"_id": "c-4", "run_id": RELAY, "scenario_id": SCENARIO, "household_id": "hh-ruiz", "ts": 250.0},  # future
    {"_id": "c-5", "run_id": RELAY, "scenario_id": SCENARIO, "household_id": "hh-vance", "ts": 10.0},  # not opted in
    # Scenario visit note: every run sees it. Exactly 72h before AS_OF, so not more than 3 days.
    {"_id": "c-6", "run_id": SCENARIO_RUN_ID, "scenario_id": SCENARIO, "household_id": "hh-pell", "ts": 168.0},
    # Another scenario's input: no run of this scenario sees it.
    {"_id": "c-7", "run_id": SCENARIO_RUN_ID, "scenario_id": "scn-other", "household_id": "hh-ruiz", "ts": 230.0},
    {"_id": "c-8", "run_id": BASELINE, "scenario_id": SCENARIO, "household_id": "hh-ruiz", "ts": 230.0},
]


def _probe(run_id, ts, household_id, *source_event_ids):
    return {"run_id": run_id, "probe_ts": ts, "household_id": household_id, "source_event_ids": list(source_event_ids)}


PROBES = [
    # Relay names everything open at h72, has no answer for hh-pell at h144 (misses pr-4), forgets
    # 8-day-old pr-1 at h216, and names pr-6 at h216 after it fell due (named but not open).
    _probe(RELAY, 72.0, "hh-vance", "ev-601"),
    _probe(RELAY, 72.0, "hh-oakes", "ev-101"),
    _probe(RELAY, 72.0, "hh-ruiz", "ev-501"),
    _probe(RELAY, 72.0, "hh-pell", "ev-602"),
    _probe(RELAY, 144.0, "hh-vance", "ev-601"),
    _probe(RELAY, 216.0, "hh-vance", "ev-503"),
    _probe(RELAY, 216.0, "hh-ruiz", "ev-502"),
    # Baseline misses pr-3 at h72 and pr-1 at h144 and h216, and names an unknown event at h216.
    _probe(BASELINE, 72.0, "hh-vance", "ev-601"),
    _probe(BASELINE, 72.0, "hh-oakes", "ev-101"),
    _probe(BASELINE, 72.0, "hh-ruiz"),
    _probe(BASELINE, 72.0, "hh-pell", "ev-602"),
    _probe(BASELINE, 144.0, "hh-vance"),
    _probe(BASELINE, 144.0, "hh-pell", "ev-602"),
    _probe(BASELINE, 216.0, "hh-vance", "ev-503", "ev-999"),
]

INPUTS = {"scenario_id": SCENARIO, "proposals": PROPOSALS, "needles": NEEDLES, "decoys": DECOYS,
          "promises": PROMISES, "registry": REGISTRY, "contacts": CONTACTS, "probes": PROBES, "as_of": AS_OF}
