#!/usr/bin/env python3
"""Build the tiny `sample_data` fixture: 1 week, 5 households, 1 needle, 1 decoy, 1 opted-in household.

    python data/gen_sample.py        # -> data/sample_data/

Hand-authored and deterministic (no randomness). Same file shapes as data/scenarios/s1 so every
worker can test against it. Households live on clearly fictional streets (config/fictional_streets.json names[34:39])
and synthetic events carry no coordinates. Real 311 rows are copied from Scenario 1 as background texture only:
they keep origin "real", carry no household, and never share an address with a synthetic household.
`example_escalations.json` holds three proposals in the evaluator's input shape plus hand-computed
verdicts and the expected `eval.scorer.score_run` result, so W4 has exact expected scores.
Authored in days since storm start; written in the contract shape by data/contract.py (hours since day 0).
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import contract
from addresses import is_real_address, normalize_address

HERE = Path(__file__).parent
OUT = HERE / "sample_data"
SID = "sample"
T0 = datetime(2021, 9, 1, 20, 0)  # noqa: DTZ001 - storm start, NY wall clock; internal ts = days since T0
DAYS = 7
FICTIONAL = {normalize_address(n) for n in json.loads((HERE / "config" / "fictional_streets.json").read_text())["names"]}
LABEL = "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."
CALLBACK = "+1-555-0100"

# (id, name, variants, number, street, unit, zip, city, age, lives_alone, language, story)
HOUSEHOLDS = [
    ("h_001", "Rosa Delgado", ["Rosa Delgado", "Mrs. Delgado", "R. Delgado", "Rosa Delgato"],
     "37-14", "Plumstone Ave", "Bsmt", "11368", "Corona", 79, True, "es", "needle:sample_n_01"),
    ("h_002", "Sun-hee Park", ["Sun-hee Park", "Mrs. Park", "S. Park"],
     "45-18", "Rushwillow St", "1F", "11358", "Flushing", 71, True, "ko", "decoy:sample_d_01"),
    ("h_003", "Farida Islam", ["Farida Islam", "Islam family", "F. Islam"],
     "86-11", "Sparrowgate Rd", "Bsmt", "11373", "Elmhurst", 41, False, "bn", "background:kept_promise"),
    ("h_004", "Tom Russo", ["Tom Russo", "Mr. Russo"],
     "69-20", "Tidewater Hollow Ln", "2F", "11377", "Woodside", 66, True, "en", "background:fine"),
    ("h_005", "Li Na Zhou", ["Li Na Zhou", "Ms. Zhou", "Zhou Li Na"],
     "142-40", "Umberfield Ave", None, "11355", "Flushing", 58, False, "zh", "background:supplies"),
]

# (ts, source, author, household, text, address_raw, household_ref_raw, fact)
SYNTHETIC = [
    (0.15, "utility", "Con Edison", None,
     ("Con Edison outage update: 42 customers without power on Plumstone Ave, 37-01 to 37-99, Corona 11368. "
      "Cause: flooding. Estimated restoration: Sep 4."),
     "Plumstone Ave, 37-01 to 37-99, Corona 11368", None, {"block": ["11368", "PLUMSTONE AVE", 37], "fact": "power_out"}),
    (0.62, "311", "311", "h_002",
     "311 call from neighbor at 45-18 RUSHWILLOW STREET 1F: no power, elderly woman lives alone, not picking up the phone.",
     "45-18 RUSHWILLOW STREET 1F", "elderly woman lives alone", {"kind": "alarm"}),
    (0.90, "utility", "Con Edison", None,
     "Con Edison outage update: power restored on Rushwillow St, 45-01 to 45-99, Flushing 11358.",
     "Rushwillow St, 45-01 to 45-99, Flushing 11358", None, {"block": ["11358", "RUSHWILLOW ST", 45], "fact": "power_restored"}),
    (1.10, "visit_note", "Volunteer Dana R.", "h_002",
     "Checked on Mrs. Park at 45-18 Rushwillow St. Power is back and she's fine. Her daughter is staying the week.",
     "45-18 Rushwillow St", "Mrs. Park", {"fact": "fine"}),
    (1.60, "visit_note", "Volunteer Omar F.", "h_003",
     ("Islam family, 4 people, basement at 86-11 Sparrowgate Rd. Water pumped out, walls still wet. "
      "Red Cross will drop off a cleaning kit tomorrow."),
     "86-11 Sparrowgate Rd, basement", "Islam family", {"fact": "promise", "id": "p1"}),
    (1.80, "visit_note", "Volunteer Alma G.", "h_001",
     ("Visited Mrs. Delgado, 79, at 37-14 Plumstone Ave, basement. Lives alone, speaks Spanish. Basement flooded, "
      "no power since Wednesday night. Her nephew Luis is coming Sunday to pump out the basement. "
      "Registered her for follow-up calls."),
     "37-14 Plumstone Ave, basement", "Mrs. Delgado", {"fact": "promise", "id": "p1"}),
    (2.60, "utility", "Con Edison", None,
     ("Con Edison outage update: restoration on Plumstone Ave, 37-01 to 37-99, Corona 11368 delayed. Flooded meter "
      "rooms in several buildings. New estimate: Sep 8 or later."),
     "Plumstone Ave, 37-01 to 37-99, Corona 11368", None, {"block": ["11368", "PLUMSTONE AVE", 37], "fact": "power_out"}),
    (2.70, "crew", "Red Cross", "h_003",
     "Red Cross drop-off: cleaning kit delivered to 86-11 Sparrowgate Rd basement (Islam).",
     "86-11 Sparrowgate Rd, basement", "Islam", {"fact": "promise_kept", "id": "p1"}),
    (3.40, "visit_note", "Volunteer Kevin L.", "h_004",
     "Tom Russo, 66, 69-20 Tidewater Hollow Ln, 2nd floor. No damage upstairs; basement storage flooded. Doing OK.",
     "69-20 Tidewater Hollow Ln, 2nd floor", "Tom Russo", {"fact": "fine"}),
    (3.90, "311", "311", "h_005",
     "311 request at 142-40 UMBERFIELD AVE: resident asks for drinking water and cleaning supplies, basement flooded.",
     "142-40 UMBERFIELD AVE", None, {"fact": "needs_supplies"}),
    (4.60, "crew", "Con Edison field crew", "h_001",
     ("Con Edison field crew: 3714 PLUMSTONE AVE basement meter room flooded, service not reconnected. "
      "Needs licensed electrician certification. No one answered the door."),
     "3714 PLUMSTONE AVE", None, {"fact": "power_out"}),
    (5.20, "crew", "Supplies team", "h_005",
     "Supplies drop: water and a cleaning kit delivered to 142-40 Umberfield Ave (Zhou).",
     "142-40 Umberfield Ave", "Zhou", {"fact": "supplies_received"}),
]


def iso(ts):
    return (T0 + timedelta(days=ts)).strftime("%Y-%m-%dT%H:%M")


def real_texture(days=5):
    """One real 311 row per day for the first `days` days of Scenario 1: background texture only."""
    real = {}
    for line in (HERE / "scenarios" / "s1" / "events.jsonl").open():
        e = json.loads(line)
        day = int(e["ts"] // 24)  # s1 is written in contract hours
        if e["origin"] == "real" and day < days and day not in real and e["address_raw"]:
            real[day] = dict(e, ts=e["ts"] / 24)
    return [real[d] for d in sorted(real)]


def build():
    hh_ids = {h[0]: f"{SID}_{h[0]}" for h in HOUSEHOLDS}
    for h in HOUSEHOLDS:
        assert normalize_address(h[4]) in FICTIONAL, f"{h[1]} is not on a fictional street"
        assert not is_real_address(f"{h[3]} {h[4]}"), f"{h[1]} would sit at a real 311 address"

    rows = [dict(e, _truth=None) for e in real_texture()]
    for ts, source, author, hh, text, address_raw, ref_raw, fact in SYNTHETIC:
        rows.append({"ts": ts, "ts_real": iso(ts), "source": source, "text": text, "address_raw": address_raw,
                     "geo": None, "household_ref_raw": ref_raw, "channel_meta": {"author": author, "language": "en"},
                     "real_311_key": None, "origin": "synthetic",
                     "_truth": {"household_id": hh_ids.get(hh), "fact": fact}})
    rows.sort(key=lambda e: (e["ts"], e["text"]))

    events, event_truth = [], {}
    for i, r in enumerate(rows, 1):
        truth = r.pop("_truth")
        e = {"event_id": f"{SID}_e_{i:06d}", "scenario_id": SID, **{k: r[k] for k in (
            "ts", "ts_real", "source", "text", "address_raw", "geo", "household_ref_raw", "channel_meta",
            "real_311_key", "origin")}}
        events.append(e)
        event_truth[e["event_id"]] = truth or {"household_id": None, "fact": None}
    eid = {e["ts"]: e["event_id"] for e in events if e["origin"] == "synthetic"}  # synthetic ts are unique

    households = [{
        "household_id": hh_ids[h[0]], "scenario_id": SID, "canonical_name": h[1], "name_variants": h[2],
        "address": {"number": h[3], "street": h[4], "unit": h[5], "zip": h[6], "city": h[7], "synthetic_number": True},
        "address_variants": sorted({f"{h[3]} {h[4]}", normalize_address(f"{h[3]} {h[4]}"), h[3].replace("-", "") + " " + h[4]}),
        "members": [{"age": h[8], "lives_alone": h[9]}], "language": h[10], "story": h[11],
        "timeline": [{"day": ts, "fact": f["fact"], "event_id": eid[ts]}
                     for ts, _, _, hh, _, _, _, f in SYNTHETIC if hh == h[0] and "fact" in f],
    } for h in HOUSEHOLDS]

    registry = [{"household_id": hh_ids["h_001"], "scenario_id": SID, "opt_in": True, "language": "es",
                 "callback_number": CALLBACK, "registered_day": 1.8, "name": "Rosa Delgado",
                 "address": "37-14 Plumstone Ave Bsmt", "registered_by": "volunteer (with consent)", "note": "Prefers Spanish."}]
    promises = [
        {"household_id": hh_ids["h_001"], "promise_id": f"{SID}_h_001_p1", "who": "nephew Luis",
         "what": "come pump out the basement", "made_day": 1.8, "due_day": 4.0, "made_in_event_id": eid[1.80],
         "status": "broken", "resolved_day": 4.0, "evidence_event_id": None},
        {"household_id": hh_ids["h_003"], "promise_id": f"{SID}_h_003_p1", "who": "Red Cross",
         "what": "drop off a cleaning kit", "made_day": 1.6, "due_day": 3.0, "made_in_event_id": eid[1.60],
         "status": "kept", "resolved_day": 2.7, "evidence_event_id": eid[2.70]},
    ]
    needles = [{"needle_id": f"{SID}_n_01", "scenario_id": SID, "household_id": hh_ids["h_001"], "kind": "broken_promise",
                "required_event_ids": [eid[1.80], eid[2.60], eid[4.60]], "deadline_day": 5.5, "danger_day": 7.0,
                "response_hours": 24, "people_at_risk": 1,
                "summary": "Nephew promised Sun Sep 5, never came; block ETA pushed to Sep 8+; flooded meter keeps her dark."}]
    decoys = [{"decoy_id": f"{SID}_d_01", "scenario_id": SID, "household_id": hh_ids["h_002"], "kind": "resolved_alarm",
               "event_ids": [eid[0.62]], "reason": "No-power alarm; block restored 7 hours later; volunteer found her fine."}]
    # Hand-computed under §5 (hours): caught = before deadline and citing >= 2 required events;
    # in time = ts + response_hours < danger_at; any decoy citation = false escalation.
    run = "sample-run"
    x1_ts = contract.hours(4.8)
    proposals = [
        {"_id": "x1", "run_id": run, "household_id": hh_ids["h_001"], "ts": x1_ts,
         "cited_event_ids": [eid[1.80], eid[2.60]],
         "expected": {"catches": f"{SID}_n_01", "reached_in_time": True, "false_escalation": False}},
        {"_id": "x2", "run_id": run, "household_id": hh_ids["h_002"], "ts": contract.hours(0.7),
         "cited_event_ids": [eid[0.62]],
         "expected": {"catches": None, "reached_in_time": None, "false_escalation": True}},
        {"_id": "x3", "run_id": run, "household_id": hh_ids["h_001"], "ts": contract.hours(6.0),
         "cited_event_ids": [eid[1.80], eid[2.60], eid[4.60]],
         "expected": {"catches": None, "reached_in_time": None, "false_escalation": False}},
    ]
    examples = {"run_id": run, "as_of": contract.hours(DAYS), "proposals": proposals,
                # schemas.Score from eval.scorer.score_run(..., contacts=[], probes=[], as_of=168)
                "expected_score": {"needle_recall": 1.0, "escalated_at": x1_ts,
                                   "impact": {"households_reached_in_time": 1, "people_reached_in_time": 1,
                                              "days_warning_gained": round((contract.hours(DAYS) - x1_ts) / 24, 6),
                                              "false_escalations": 1},
                                   "goal": {"promises_on_time_pct": 50.0, "silent_households": 1},
                                   "false_escalation_decoy_ids": [f"{SID}_d_01"]}}
    scenario = {"scenario_id": SID, "title": "Sample week", "borough": "Queens", "t0": T0.isoformat(),
                "ts_unit": "days since storm start", "days": DAYS, "label": LABEL, "callback_number": CALLBACK,
                "counts": {"events": len(events), "real": sum(e["origin"] == "real" for e in events),
                           "households": len(households), "registry": len(registry), "needles": 1, "decoys": 1}}
    return {"events.jsonl": [contract.event(e) for e in events], "event_truth.json": event_truth,
            "households_truth.json": [contract.household(h) for h in households],
            "registry.json": [contract.registry_entry(r) for r in registry],
            "promises.json": [contract.promise(p) for p in promises],
            "needles.json": [contract.needle(n) for n in needles], "decoys.json": decoys,
            "example_escalations.json": examples, "scenario.json": contract.scenario_meta(scenario)}


def main(out=OUT):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in build().items():
        if name.endswith(".jsonl"):
            (out / name).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in data))
        else:
            (out / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
