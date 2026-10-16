#!/usr/bin/env python3
"""The Scenario 1 gate: Data Spec §7 plus the W5-C2 integration rules.

    python data/validate.py            # validates data/scenarios/s1, includes a regeneration check
    python data/validate.py s1 --fast  # skip the regeneration check
"""
import filecmp
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from addresses import is_real_address, normalize_address

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))  # the repo root: shared contracts and W2's matcher
from memory.households import normalize as w2_normalize
from schemas import Decoy, Needle, RegistryEntry, TruthPromise

LABEL = "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."

HERE = Path(__file__).parent
EVENT_FIELDS = {"_id", "run_id", "scenario_id", "ts", "ts_real", "source", "text", "address_raw", "geo",
                "household_ref_raw", "channel_meta", "real_311_key", "origin"}
HIDDEN_FROM_RELAY = {"origin"}
SOURCES = {"311", "visit_note", "utility", "crew", "call"}

failures = []


def promise_ok(p, by_id, truth):
    """Made in its source event, due after that, and kept (with evidence at status_ts) or lapsed (at due, none)."""
    made = by_id.get(p["source_event_id"])
    if made is None or truth[p["source_event_id"]]["household_id"] != p["household_id"]:
        return False
    if abs(made["ts"] - p["made_ts"]) > 0.25 or not p["made_ts"] < p["due_ts"]:
        return False
    if p["status"] == "kept":
        return bool(p["evidence_event_ids"]) and all(abs(by_id[i]["ts"] - p["status_ts"]) <= 0.25
                                                     for i in p["evidence_event_ids"])
    return not p["evidence_event_ids"] and p["status_ts"] == p["due_ts"]


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        failures.append(msg)


def main():
    scenario = next((a for a in sys.argv[1:] if not a.startswith("--")), "s1")
    d = HERE / "scenarios" / scenario
    events = [json.loads(line) for line in (d / "events.jsonl").open()]
    by_id = {e["_id"]: e for e in events}
    households = json.loads((d / "households_truth.json").read_text())
    registry = json.loads((d / "registry.json").read_text())
    needles = json.loads((d / "needles.json").read_text())
    decoys = json.loads((d / "decoys.json").read_text())
    truth = json.loads((d / "event_truth.json").read_text())
    hh_ids = {h["household_id"] for h in households}

    print("1. counts by source and day (spike, then long tail)")
    by_day = Counter(int(e["ts"] // 24) for e in events)  # ts = hours since day 0
    print("     by source:", dict(sorted(Counter(e["source"] for e in events).items())))
    print("     by day:", " ".join(f"{k}:{by_day[k]}" for k in range(43)))
    early = sum(by_day[k] for k in range(4)) / 4
    late = sum(by_day[k] for k in range(4, 43)) / 39
    check(early > 2 * late, f"days 0-3 avg {early:.0f}/day vs days 4-42 avg {late:.0f}/day")
    check(sum(by_day[k] for k in range(30, 43)) > 0, "long tail reaches the last two weeks")

    print("2. real vs synthetic ~70/30")
    share = sum(e["origin"] == "real" for e in events) / len(events)
    check(0.65 <= share <= 0.75, f"real share {share:.1%} of {len(events)} events")

    print("3. no synthetic household at a real address")
    hits = [h["household_id"] for h in households
            if is_real_address(f"{h['address']['number']} {h['address']['street']}")]
    check(not hits, f"blocklist hits: {hits}")
    fictional = {normalize_address(n) for n in json.loads((HERE / "config" / "fictional_streets.json").read_text())["names"]}
    off = [h["household_id"] for h in households if normalize_address(h["address"]["street"]) not in fictional]
    check(not off, f"every household on a fictional street (off: {off})")
    fine = [e["_id"] for e in events if e["origin"] != "real" and e["geo"]
            and (round(e["geo"]["lat"], 2), round(e["geo"]["lng"], 2)) != (e["geo"]["lat"], e["geo"]["lng"])]
    check(not fine, f"synthetic coordinates are ZIP-level (<= 2 decimals) or absent ({len(fine)} too precise)")

    print("4. needles: >=2 required events, >=2 sources, all before the deadline")
    for n in needles:
        req = [by_id.get(i) for i in n["required_event_ids"]]
        exists = all(req)
        sources = {e["source"] for e in req if e}
        before = all(e["ts"] < n["deadline"] for e in req if e)
        own = all(truth[i]["household_id"] in (n["household_id"], None) for i in n["required_event_ids"])
        check(exists and len(req) >= 2 and len(sources) >= 2 and before and own
              and n["deadline"] < n["danger_at"] and 12 <= n["response_hours"] <= 48,
              f"{n['needle_id']} {n['kind']}: {len(req)} events, sources {sorted(sources)}, "
              f"deadline h {n['deadline']:.1f}, danger h {n['danger_at']:.1f}")
    check(8 <= len(needles) <= 12, f"{len(needles)} needles")
    check(8 <= len(decoys) <= 12, f"{len(decoys)} decoys")
    check(all(i in by_id for dcy in decoys for i in dcy["event_ids"]), "every decoy event exists")
    check(not {i for n in needles for i in n["required_event_ids"]} & {i for dc in decoys for i in dc["event_ids"]},
          "no event is both a needle requirement and a decoy")

    print("5. human review: see REVIEW.md")

    print("6. events consistent with truth (structural)")
    bad = []
    for h in households:
        for f in h["timeline"]:
            if f["fact"] == "promise" and abs(by_id[f["event_id"]]["ts"] - f["ts"]) > 0.25:
                bad.append(f"{h['household_id']} promise {f['id']} made at h {f['ts']} but event at "
                           f"{by_id[f['event_id']]['ts']}")
            if f["fact"] == "promise_kept" and f.get("event_id") and abs(by_id[f["event_id"]]["ts"] - f["ts"]) > 0.25:
                bad.append(f"{h['household_id']} promise {f['id']} kept at h {f['ts']} but evidence at "
                           f"{by_id[f['event_id']]['ts']}")
    check(not bad, f"promise facts match their events ({len(bad)} mismatches)")
    for b in bad[:5]:
        print("     ", b)
    end = json.loads((d / "scenario.json").read_text())["end_ts"]
    check(all(0 <= e["ts"] < end for e in events), f"every event ts in [0, {end}) hours")
    check(all(e["run_id"] == "scenario" for e in events), "scenario inputs carry run_id 'scenario'")
    check(all(r["household_id"] in hh_ids and r["opt_in"] for r in registry), "registry entries are real, opted-in")
    silent = [n for n in needles if n["kind"] == "silent_household"]
    reg = {r["household_id"] for r in registry}
    check(all(n["household_id"] in reg for n in silent), "every silent-household needle is opted in")

    print("7. visibility")
    check(all(set(e) == EVENT_FIELDS for e in events), "events carry exactly the contract + spec fields")
    check(all(e["source"] in SOURCES for e in events), "sources in the closed set")
    check(not any("household_id" in e for e in events), "no household_id on events")
    check(len(by_id) == len(events), "event ids unique")
    visible = [{k: v for k, v in e.items() if k not in HIDDEN_FROM_RELAY} for e in events[:1]]
    check("origin" not in visible[0], f"runtime reader strips {sorted(HIDDEN_FROM_RELAY)}")

    print("9. C2 integration rules")
    meta = json.loads((d / "scenario.json").read_text())
    promises = json.loads((d / "promises.json").read_text())
    contact_path = d / "contact_truth.json"
    ct = json.loads(contact_path.read_text()) if contact_path.exists() else None
    by_hh = {h["household_id"]: h for h in households}
    check(meta["label"] == LABEL, "canonical on-screen label")
    revision = hashlib.sha256((d / "events.jsonl").read_bytes()).hexdigest()[:16]
    if "revision" in meta:
        stamps = {meta["revision"], *(n["revision"] for n in needles), *(x["revision"] for x in decoys)}
        stamps |= {ct["revision"]} if ct else set()
        check(stamps == {revision}, f"scenario, needles, decoys and contact truth all stamp revision {revision}")
    for key, docs, shape in (("needles", needles, Needle), ("decoys", decoys, Decoy),
                             ("registry", registry, RegistryEntry), ("promises", promises, TruthPromise)):
        check(all(shape.__required_keys__ <= set(doc) for doc in docs), f"{key} carry the schemas.py required keys")
    for key, field, docs in (("households", "household_id", households), ("needles", "needle_id", needles),
                             ("decoys", "decoy_id", decoys), ("promises", "promise_id", promises),
                             ("registry", "household_id", registry)):
        ids = [doc[field] for doc in docs]
        check(len(ids) == len(set(ids)), f"no duplicate {key} ids")
    names = [h["canonical_name"] for h in households]
    check(len(names) == len(set(names)), "synthetic full names are unique (namesakes share a surname only)")

    if "identity_address" in households[0]:
        bad = [r["household_id"] for r in registry if r["household_id"] not in by_hh
               or r["name"] != by_hh[r["household_id"]]["canonical_name"]
               or r["address"] != by_hh[r["household_id"]]["identity_address"]
               or r["language"] != by_hh[r["household_id"]]["language"]
               or not 0 <= r["registered_ts"] < meta["end_ts"]]
        check(not bad, f"registry entries match their households' identity and language ({bad})")
        unmatched = []
        for n in needles:
            key = w2_normalize(by_hh[n["household_id"]]["identity_address"])
            hits = [by_id[i] for i in n["required_event_ids"]
                    if by_id[i]["address_raw"] and w2_normalize(by_id[i]["address_raw"]) == key]
            if len(hits) < 2 or len({e["source"] for e in hits}) < 2:
                unmatched.append(n["needle_id"])
        check(not unmatched, f"every needle has >=2 required events from >=2 services that W2's matcher resolves "
                             f"to the household ({unmatched})")
        identities = {w2_normalize(h["identity_address"]): h["household_id"] for h in households}
        stray = [i for x in decoys for i in x["event_ids"] + x["resolution_event_ids"]
                 if by_id[i]["address_raw"] and identities.get(w2_normalize(by_id[i]["address_raw"]),
                                                               x["household_id"]) != x["household_id"]]
        check(not stray, f"no decoy or namesake event resolves to another household ({stray})")

        # Visible data only: file households from named+addressed reports (W2's matcher), then compare with truth.
        from filing import file_households

        resolved, filed = file_households(events, registry)
        registered = {r["household_id"] for r in registry}
        unreachable = []
        for n in needles:
            homes = {resolved.get(i) for i in n["required_event_ids"]} - {None}
            home = next(iter(homes)) if len(homes) == 1 else None
            hits = [by_id[i] for i in n["required_event_ids"] if home and resolved.get(i) == home]
            owners = {truth[e]["household_id"] for e, h in resolved.items() if h == home}
            expected_home = n["household_id"] if n["household_id"] in registered else home in filed and home
            if home is None or home != expected_home or len({e["source"] for e in hits}) < 2 \
                    or any(e["ts"] >= n["deadline"] for e in hits) or owners != {n["household_id"]}:
                unreachable.append(n["needle_id"])
        check(not unreachable, f"all {len(needles)} needles structurally reachable from visible data: registered ones "
                               f"via the registry, the rest filed from a named+addressed report; >=2 required events "
                               f"from >=2 services before the deadline ({unreachable})")
        by_decoy = {x["decoy_id"]: x for x in decoys}
        n07 = next((n for n in needles if n["needle_id"].endswith("_n_07")), None)

        def homes_of(ids):
            return {resolved.get(i) for i in ids} - {None}

        traps = []
        if n07 and "s1_d_09" in by_decoy and homes_of(n07["required_event_ids"]) & homes_of(by_decoy["s1_d_09"]["event_ids"]):
            traps.append("Wang cellar / Wang 3F")
        if {"s1_d_10", "s1_d_11"} <= set(by_decoy) and \
                homes_of(by_decoy["s1_d_10"]["event_ids"]) & homes_of(by_decoy["s1_d_11"]["event_ids"]):
            traps.append("Gonzalez 1F / Gonzalez basement")
        check(not traps, f"unit/namesake traps stay separate ({traps})")
        linked = sorted(e["_id"] for e in events if e["origin"] == "real" and (e["_id"] in resolved or truth[e["_id"]]["household_id"]))
        check(not linked, f"no real 311 event is linked to a synthetic household ({len(linked)} linked)")

    unresolved = [x["decoy_id"] for x in decoys if not x.get("resolution_event_ids") or any(
        by_id[i]["ts"] < max(by_id[a]["ts"] for a in x["event_ids"]) or truth[i]["household_id"] != x["household_id"]
        for i in x["resolution_event_ids"])]
    check(not unresolved, f"every decoy has a visible resolution at or after its alarm ({unresolved})")

    bad = [p["promise_id"] for p in promises if not promise_ok(p, by_id, truth)]
    check(not bad, f"truth promises: source event, timing and kept/lapsed evidence consistent ({bad})")

    if ct is not None:
        opted = {r["household_id"]: r for r in registry}
        check({h["household_id"] for h in ct["households"]} == set(opted) and all(r["opt_in"] is True for r in registry),
              "contact truth covers exactly the opted-in households, and nobody else")
        silent = {n["household_id"]: n for n in needles if n["kind"] == "silent_household"}
        long_quiet = {h["household_id"] for h in ct["households"]
                      if any(w["until_ts"] - w["from_ts"] > 72 for w in h["no_answer"])}
        hero = [n["household_id"] for n in needles if n["needle_id"].endswith("_n_01")]
        check(long_quiet == set(silent) | set(hero), "only the silent-household needles and the hero go quiet > 72h")
        covered = all(any(opted[k]["registered_ts"] <= w["from_ts"] and w["from_ts"] + 72 < n["deadline"] <= w["until_ts"]
                          for w in next(h for h in ct["households"] if h["household_id"] == k)["no_answer"])
                      for k, n in silent.items())
        check(covered, "each silent needle's no-answer window makes silence > 72h certain before its deadline")

    if (d / "manifest.json").exists():
        print("10. frozen demo seed (manifest.json)")
        from freeze import verify

        problems = verify(d)
        check(not problems, f"committed files, revision, day0, end_ts, label and the Mrs. Chen anchors match the "
                            f"frozen manifest ({problems})")

    if "--fast" not in sys.argv:
        print("11. regeneration with the same seed is byte-identical")
        if not (HERE / "derived" / "events_311.jsonl").exists():
            check(False, "regeneration needs data/derived/events_311.jsonl: run `python data/pull_311.py extract` "
                         "and `python data/load_311.py` first")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run([sys.executable, str(HERE / "gen_scenario.py"), tmp], check=True, capture_output=True)
                names = sorted(p.name for p in d.iterdir() if p.is_file() and p.name != "manifest.json")
                _, mismatch, errors = filecmp.cmpfiles(d, tmp, names, shallow=False)
                check(not mismatch and not errors, f"{len(names)} files identical (mismatch: {mismatch + errors})")

    print(f"\n{'PASS' if not failures else 'FAIL'}: {len(failures)} failing checks")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
