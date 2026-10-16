"""W5-C1 acceptance gates over the committed fixtures (data/sample_data, data/scenarios/s1)."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1]
ROOT = DATA.parent
sys.path[:0] = [str(DATA), str(ROOT)]  # data/ scripts are plain modules; schemas/interfaces live at the root

import contact
import contract
import freeze
import gen_sample
from addresses import is_real_address, normalize_address

from interfaces import event_visible_to_run
from schemas import SCENARIO_RUN_ID, Decoy, Event, Needle, RegistryEntry, TruthPromise

DAY0 = datetime.fromisoformat(contract.DAY0)
LABEL = "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."
SCENARIOS = {"sample": DATA / "sample_data", "s1": DATA / "scenarios" / "s1"}
FICTIONAL = {normalize_address(n) for n in json.loads((DATA / "config" / "fictional_streets.json").read_text())["names"]}
REAL_STREETS = {s["street"] for s in json.loads((DATA / "derived" / "street_intensity.json").read_text())["streets"]}


UNIT = re.compile(r"\b(BSMT|BASEMENT|CELLAR|APT \w+|\d+F|\d+(ST|ND|RD|TH)? FLOOR|FLOOR)\b")


def load(name):
    d = SCENARIOS[name]

    def read(f):
        return json.loads((d / f).read_text())

    return {"events": [json.loads(line) for line in (d / "events.jsonl").open()],
            **{k: read(f"{k}.json") for k in ("event_truth", "households_truth", "registry", "promises",
                                               "needles", "decoys", "scenario")}}


@pytest.fixture(scope="module", params=list(SCENARIOS))
def scenario(request):
    return request.param, load(request.param)


def street_address(raw):
    """House-numbered forms of an address, normalized and unit-free: '3714 104 ST' -> {'3714 104 ST', '37-14 104 ST'}.

    Street-only mentions ('Hollow Oak Ln, basement') name no dwelling and return nothing.
    """
    base = UNIT.sub("", normalize_address(raw.split(",")[0])).split()
    if len(base) < 2 or not re.fullmatch(r"\d+-\d+[A-Z]?|\d{4,5}", base[0]):
        return set()
    forms = {" ".join(base)}
    if base[0].isdigit():
        forms.add(" ".join([f"{base[0][:-2]}-{base[0][-2:]}", *base[1:]]))
    return forms


def test_documents_match_the_shared_contract(scenario):
    name, s = scenario
    assert contract.SCENARIO_RUN_ID == SCENARIO_RUN_ID
    assert s["scenario"]["day0"] == contract.DAY0 and s["scenario"]["end_ts"] == s["scenario"]["days"] * 24
    for e in s["events"]:
        assert Event.__required_keys__ <= set(e) and e["run_id"] == SCENARIO_RUN_ID and e["scenario_id"] == name
        assert isinstance(e["ts"], (int, float)) and event_visible_to_run(e, "any-run", name)
    for key, shape in (("needles", Needle), ("decoys", Decoy), ("registry", RegistryEntry), ("promises", TruthPromise)):
        assert all(shape.__required_keys__ <= set(doc) for doc in s[key]), key
    # Every other key is either in the contract or a documented W5 extra.
    extras = {"registry": {"registered_by", "note"}, "promises": {"promise_id", "who", "what", "evidence_event_ids"}}
    for key, shape in (("registry", RegistryEntry), ("promises", TruthPromise)):
        allowed = set(shape.__annotations__) | extras[key]
        assert all(set(doc) <= allowed for doc in s[key]), (key, set().union(*map(set, s[key])) - allowed)
    assert all(r["scenario_id"] == name and isinstance(r["registered_ts"], (int, float)) for r in s["registry"])
    assert all(p["status"] in ("kept", "lapsed") and p["made_ts"] < p["due_ts"] for p in s["promises"])
    assert all(r["first_name"] and r["name"].startswith(r["first_name"]) for r in s["registry"])


def test_label_is_the_canonical_on_screen_label(scenario):
    _, s = scenario
    assert s["scenario"]["label"] == LABEL


def test_no_duplicate_ids(scenario):
    _, s = scenario
    for key, field in [("events", "_id"), ("households_truth", "household_id"), ("needles", "needle_id"),
                       ("decoys", "decoy_id"), ("promises", "promise_id"), ("registry", "household_id")]:
        ids = [x[field] for x in s[key]]
        assert len(ids) == len(set(ids)), f"duplicate {field} in {key}"
    assert not {n["needle_id"] for n in s["needles"]} & {d["decoy_id"] for d in s["decoys"]}


def test_event_ordering_is_deterministic(scenario):
    name, s = scenario
    keys = [(e["ts"], e["_id"]) for e in s["events"]]
    assert keys == sorted(keys), "events.jsonl is not in the runtime's (ts, _id) cursor order"
    assert [e["_id"] for e in s["events"]] == [f"{name}_e_{i:06d}" for i in range(1, len(keys) + 1)]
    assert all(0 <= ts < s["scenario"]["end_ts"] for ts, _ in keys)
    assert set(s["event_truth"]) == {e["_id"] for e in s["events"]}


def test_sample_regenerates_identically():
    built = gen_sample.build()
    for name, data in built.items():
        path = SCENARIOS["sample"] / name
        committed = [json.loads(line) for line in path.open()] if name.endswith(".jsonl") else json.loads(path.read_text())
        assert committed == json.loads(json.dumps(data)), f"{name} differs from gen_sample.build()"


def test_real_311_rows_are_kept_apart_from_synthetic_people(scenario):
    _, s = scenario
    for e in s["events"]:
        truth = s["event_truth"][e["_id"]]
        if e["origin"] == "real":
            assert e["real_311_key"] and truth["household_id"] is None, f"real row {e['_id']} tied to a person"
        else:
            assert e["real_311_key"] is None, f"synthetic event {e['_id']} claims a real 311 key"
    assert not any("household_id" in e for e in s["events"]), "events must not reveal household_id"


def test_synthetic_people_never_sit_at_real_311_addresses(scenario):
    _, s = scenario
    real = set().union(*(street_address(e["address_raw"]) for e in s["events"] if e["origin"] == "real" and e["address_raw"]))
    for h in s["households_truth"]:
        a = h["address"]
        forms = street_address(f"{a['number']} {a['street']}")
        for v in h["address_variants"]:
            forms |= street_address(v)
        assert not any(is_real_address(f) for f in forms), f"{h['household_id']} is at a real 311 address"
        assert not forms & real, f"{h['household_id']} shares an address with a real 311 row"
    for e in s["events"]:
        hid = s["event_truth"][e["_id"]]["household_id"]
        if hid and e["address_raw"] and " to " not in e["address_raw"]:  # skip block-level ranges
            assert not any(is_real_address(f) for f in street_address(e["address_raw"])), e["_id"]


def fictional_street_in(address):
    """The fictional street an address names ('4122 HOLLOW OAK LN', 'Hollow Oak Ln, 41-01 to 41-99, ...'), else None."""
    norm = normalize_address(address)
    return next((f for f in FICTIONAL if re.search(rf"(^|[\s,]){re.escape(f)}($|[\s,#])", norm)), None)


def test_fictional_street_set_shares_nothing_with_real_311_streets():
    assert len(FICTIONAL) >= 40 and not FICTIONAL & REAL_STREETS
    words = {w for street in FICTIONAL for w in street.split()[:-1]}
    assert not any(w in real.split() for real in REAL_STREETS for w in words if len(w) > 3)


def test_synthetic_people_live_only_on_fictional_streets(scenario):
    _, s = scenario
    for h in s["households_truth"]:
        assert normalize_address(h["address"]["street"]) in FICTIONAL, h["household_id"]
        assert all(fictional_street_in(v) for v in h["address_variants"]), h["household_id"]
    for e in s["events"]:
        if e["origin"] != "real" and e["address_raw"]:
            assert fictional_street_in(e["address_raw"]), f"{e['_id']} names a non-fictional street: {e['address_raw']}"
    for r in s["registry"]:
        assert fictional_street_in(r["address"]), r["household_id"]


def test_synthetic_coordinates_are_coarse_or_absent(scenario):
    _, s = scenario
    per_zip = {}
    for e in s["events"]:
        if e["origin"] == "real" or e["geo"] is None:
            continue
        lat, lng = e["geo"]["lat"], e["geo"]["lng"]
        assert (round(lat, 2), round(lng, 2)) == (lat, lng), f"{e['_id']} has a property-level coordinate"
        hid = s["event_truth"][e["_id"]]["household_id"]
        zip_ = next(h["address"]["zip"] for h in s["households_truth"] if h["household_id"] == hid) if hid else None
        if zip_:
            per_zip.setdefault(zip_, set()).add((lat, lng))
    assert all(len(points) == 1 for points in per_zip.values()), "one ZIP-level point per ZIP"
    assert not any("geo" in h for h in s["households_truth"])


def test_needles_and_decoys_resolve(scenario):
    _, s = scenario
    by_id = {e["_id"]: e for e in s["events"]}
    households = {h["household_id"] for h in s["households_truth"]}
    for n in s["needles"]:
        req = [by_id[i] for i in n["required_event_ids"]]
        assert n["household_id"] in households and len(req) >= 2 and len({e["source"] for e in req}) >= 2
        assert all(e["ts"] < n["deadline"] < n["danger_at"] for e in req)
        assert all(s["event_truth"][i]["household_id"] in (n["household_id"], None) for i in n["required_event_ids"])
    for d in s["decoys"]:
        assert d["household_id"] in households and all(i in by_id for i in d["event_ids"])
    registry = {r["household_id"] for r in s["registry"]}
    assert registry <= households and all(r["opt_in"] for r in s["registry"])


def test_sample_has_the_brief_counts():
    s = load("sample")
    assert (len(s["households_truth"]), len(s["needles"]), len(s["decoys"]), len(s["registry"])) == (5, 1, 1, 1)
    assert s["scenario"]["days"] == 7


def test_mrs_chen_demo_chain():
    s = load("s1")
    by_id = {e["_id"]: e for e in s["events"]}
    chen = next(h for h in s["households_truth"] if h["canonical_name"] == "Mei Chen")
    needle = next(n for n in s["needles"] if n["household_id"] == chen["household_id"])
    assert needle["needle_id"] == "s1_n_01" and needle["kind"] == "broken_promise"
    visit, delay, crew = (by_id[i] for i in needle["required_event_ids"])
    assert [e["source"] for e in (visit, delay, crew)] == ["visit_note", "utility", "crew"]
    assert visit["ts"] < delay["ts"] < crew["ts"] < needle["deadline"] < needle["danger_at"]
    for e in (visit, delay, crew):  # every ts (hours since day 0) matches its wall-clock time
        assert (DAY0 + timedelta(hours=e["ts"])).strftime("%Y-%m-%dT%H:%M") == e["ts_real"][:16]
    assert (visit["ts"] + 20) // 24 == 2, "visit note falls on calendar day 2 (Fri Sep 3)"
    assert "Chen" in visit["text"] and "Tuesday" in visit["text"] and "son" in visit["text"]
    assert "Sep 13" in delay["text"] and "Hollow Oak Ln" in delay["text"]
    assert chen["address"]["number"] == "41-22" and chen["address"]["street"] == "Hollow Oak Ln"
    promise = next(p for p in s["promises"] if p["household_id"] == chen["household_id"])
    assert promise["source_event_id"] == visit["_id"] and promise["status"] == "lapsed"
    assert visit["ts"] < promise["due_ts"] < needle["deadline"]
    reg = next(r for r in s["registry"] if r["household_id"] == chen["household_id"])
    assert reg["opt_in"] and reg["language"] == "zh" and reg["first_name"] == "Mei"
    assert reg["registered_ts"] <= visit["ts"] + 1.2


def verdict(proposal, needles, decoys):
    """Reference reading of the IMPLEMENTATION_PLAN §5 rule (hours), for W4 to match."""
    cited = set(proposal["cited_event_ids"])
    caught = next((n for n in needles if proposal["ts"] < n["deadline"]
                   and len(cited & set(n["required_event_ids"])) >= 2), None)
    return {"catches": caught["needle_id"] if caught else None,
            "reached_in_time": (proposal["ts"] + caught["response_hours"] < caught["danger_at"]) if caught else None,
            "false_escalation": any(cited & set(d["event_ids"]) for d in decoys)}


def test_sample_fixture_has_exact_expected_verdicts():
    s = load("sample")
    examples = json.loads((SCENARIOS["sample"] / "example_escalations.json").read_text())
    assert [p["_id"] for p in examples["proposals"]] == ["x1", "x2", "x3"]
    for p in examples["proposals"]:
        assert p["run_id"] == examples["run_id"]
        assert verdict(p, s["needles"], s["decoys"]) == p["expected"], p["_id"]


def test_w4_scorer_scores_the_sample_fixture():
    scorer = pytest.importorskip("eval.scorer", reason="W4 evaluator (eval/) is not on this branch yet")
    s = load("sample")
    examples = json.loads((SCENARIOS["sample"] / "example_escalations.json").read_text())
    score = scorer.score_run(examples["run_id"], scenario_id="sample", proposals=examples["proposals"],
                             needles=s["needles"], decoys=s["decoys"], promises=s["promises"], registry=s["registry"],
                             contacts=[], probes=[], as_of=examples["as_of"])
    want = examples["expected_score"]
    (result,) = score["detail"]["needles"]
    assert (score["needle_recall"], result["escalated_at"]) == (want["needle_recall"], want["escalated_at"])
    assert score["impact"] == pytest.approx(want["impact"]) and score["goal"] == want["goal"]
    assert score["detail"]["false_escalation_decoy_ids"] == want["false_escalation_decoy_ids"]
    s1 = load("s1")  # the full scenario's ground truth is scorable too (an empty run catches nothing)
    empty = scorer.score_run("empty-run", scenario_id="s1", proposals=[], needles=s1["needles"], decoys=s1["decoys"],
                             promises=s1["promises"], registry=s1["registry"], contacts=[], probes=[],
                             as_of=s1["scenario"]["end_ts"])
    assert empty["needle_recall"] == 0 and len(empty["detail"]["needles"]) == len(s1["needles"])


# ---------- W5-C2: frozen Scenario 1 ----------

def test_mrs_chen_demo_path_is_pinned():
    """visit note -> son promise -> Con Ed delay -> crew / no answer -> silence follow-up -> eventual call."""
    s = load("s1")
    by_id = {e["_id"]: e for e in s["events"]}
    hero = next(n for n in s["needles"] if n["needle_id"] == "s1_n_01")
    assert hero["household_id"] == "s1_h_001" and hero["kind"] == "broken_promise"
    assert [(i, by_id[i]["source"], by_id[i]["ts"], by_id[i]["ts_real"]) for i in hero["required_event_ids"]] == [
        ("s1_e_000376", "visit_note", 42.6, "2021-09-03T14:36"),   # Fri: son Wei is coming Tuesday
        ("s1_e_000818", "utility", 158.729, "2021-09-08T10:43"),   # Wed: Con Ed pushes the block to Sep 13+
        ("s1_e_001073", "crew", 303.0, "2021-09-14T11:00"),        # flooded meter, no one answered the door
    ]
    assert (hero["deadline"], hero["danger_at"], hero["response_hours"]) == (528.0, 600.0, 24)
    visit = by_id["s1_e_000376"]
    assert (visit["address_raw"], visit["household_ref_raw"]) == ("41-22 Hollow Oak Ln", "Mrs. Chen")
    assert "41-22 Hollow Oak Lane" in visit["text"] and "son Wei is coming Tuesday" in visit["text"]
    promise = next(p for p in s["promises"] if p["household_id"] == "s1_h_001")
    assert (promise["source_event_id"], promise["made_ts"], promise["due_ts"], promise["status"]) == (
        "s1_e_000376", 42.6, 144.0, "lapsed")
    reg = next(r for r in s["registry"] if r["household_id"] == "s1_h_001")
    assert (reg["name"], reg["address"], reg["language"], reg["registered_ts"]) == (
        "Mei Chen", "41-22 Hollow Oak Ln", "zh", 43.008)
    truth = contact.load(SCENARIOS["s1"] / "contact_truth.json")["s1_h_001"]
    assert [(w["from_ts"], w["until_ts"]) for w in truth["no_answer"]] == [(145.5, 493.0)]
    assert contact.answers(truth, 145.0) and not contact.answers(truth, 150.0) and not contact.answers(truth, 492.9)
    assert contact.line(truth, 150.0) is not None and contact.answers(truth, 493.0)
    assert contact.line(truth, 493.0).startswith("My son never came")
    assert 145.5 + 72 < hero["deadline"], "the silence follow-up is due before the deadline"


def test_artifacts_come_from_one_generated_revision():
    """Needles, decoys and contact truth must reference this exact event stream, never an older regeneration."""
    revision = hashlib.sha256((SCENARIOS["s1"] / "events.jsonl").read_bytes()).hexdigest()[:16]
    s = load("s1")
    ct = json.loads((SCENARIOS["s1"] / "contact_truth.json").read_text())
    assert s["scenario"]["revision"] == ct["revision"] == revision
    assert all(n["revision"] == revision for n in s["needles"]) and all(d["revision"] == revision for d in s["decoys"])
    by_id = {e["_id"]: e for e in s["events"]}
    streets = {h["household_id"]: h["address"]["street"] for h in s["households_truth"]}
    for n in s["needles"]:
        for event_id in n["required_event_ids"]:
            owner, event = s["event_truth"][event_id]["household_id"], by_id[event_id]
            assert owner == n["household_id"] or (owner is None and event["source"] == "utility"
                                                   and streets[n["household_id"]] in event["address_raw"]), event_id


def test_decoys_have_a_visible_resolution():
    s = load("s1")
    by_id = {e["_id"]: e for e in s["events"]}
    for d in s["decoys"]:
        alarm = max(by_id[i]["ts"] for i in d["event_ids"])
        assert d["resolution_event_ids"], d["decoy_id"]
        for event_id in d["resolution_event_ids"]:
            assert by_id[event_id]["ts"] >= alarm and s["event_truth"][event_id]["household_id"] == d["household_id"]


def test_contact_truth_makes_silence_reproducible():
    s = load("s1")
    ct = json.loads((SCENARIOS["s1"] / "contact_truth.json").read_text())
    registered = {r["household_id"]: r for r in s["registry"]}
    assert {h["household_id"] for h in ct["households"]} == set(registered), "calls only reach opted-in households"
    end = s["scenario"]["end_ts"]
    for h in ct["households"]:
        assert h["script"] and h["script"][0]["from_ts"] == 0.0 and h["script"] == sorted(h["script"], key=lambda x: x["from_ts"])
        assert all(0 <= w["from_ts"] < w["until_ts"] <= end for w in h["no_answer"])
    silent = {n["household_id"]: n for n in s["needles"] if n["kind"] == "silent_household"}
    long_silences = {h["household_id"] for h in ct["households"]
                     if any(w["until_ts"] - w["from_ts"] > 72 for w in h["no_answer"])}
    assert long_silences == set(silent) | {"s1_h_001"}, "only the silent needles and the hero go quiet for > 72h"
    by_household = {h["household_id"]: h for h in ct["households"]}
    for household_id, n in silent.items():
        (window,) = by_household[household_id]["no_answer"]
        assert registered[household_id]["registered_ts"] <= window["from_ts"]
        assert window["from_ts"] + 72 < n["deadline"] <= window["until_ts"], n["needle_id"]


def test_synthetic_full_names_are_unique():
    names = [h["canonical_name"] for h in load("s1")["households_truth"]]
    assert len(names) == len(set(names)), "a namesake must be a deliberate trap (shared surname), never a duplicate"


# ---------- W5-C3: frozen demo seed ----------

def test_scenario_1_matches_its_frozen_manifest():
    assert freeze.verify() == []
    manifest = json.loads((SCENARIOS["s1"] / "manifest.json").read_text())
    assert set(manifest) == {"scenario_id", "seed", "revision", "day0", "end_ts", "label", "sha256", "mrs_chen"}
    assert set(manifest["sha256"]) == set(freeze.ARTIFACTS)
    assert manifest["revision"] == manifest["sha256"]["events.jsonl"][:16] == load("s1")["scenario"]["revision"]
    assert manifest["label"] == LABEL and (manifest["seed"], manifest["end_ts"]) == (21, 1032)
    # Visible anchors only: everything in mrs_chen is already in registry.json or events.jsonl.
    s = load("s1")
    entry = next(r for r in s["registry"] if r["household_id"] == manifest["mrs_chen"]["household_id"])
    assert (entry["name"], entry["address"]) == (manifest["mrs_chen"]["name"], manifest["mrs_chen"]["address"])
    by_id = {e["_id"]: e for e in s["events"]}
    for key in ("visit_note", "utility_delay", "crew"):
        a = manifest["mrs_chen"][key]
        e = by_id[a["event_id"]]
        assert (e["source"], e["ts"], e["ts_real"]) == (a["source"], a["ts"], a["ts_real"])


@pytest.mark.parametrize("tamper", ["events", "label", "chen"])
def test_the_freeze_catches_any_change(tmp_path, tamper):
    copy = tmp_path / "s1"
    shutil.copytree(SCENARIOS["s1"], copy)
    assert freeze.verify(copy) == []
    if tamper == "events":
        data = bytearray((copy / "events.jsonl").read_bytes())
        data[-2:-1] = b" "
        (copy / "events.jsonl").write_bytes(bytes(data))
    elif tamper == "label":
        meta = json.loads((copy / "scenario.json").read_text())
        meta["label"] = "Something else."
        (copy / "scenario.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    else:
        lines = (copy / "events.jsonl").read_text().splitlines()
        lines = [line.replace('"ts": 42.6,', '"ts": 43.6,') if '"s1_e_000376"' in line else line for line in lines]
        (copy / "events.jsonl").write_text("\n".join(lines) + "\n")
    problems = freeze.verify(copy)
    assert problems and any(("events.jsonl" in p) or ("scenario.json" in p) or ("label" in p) for p in problems)
    if tamper == "chen":
        assert any("mrs_chen" in p for p in problems)


def test_regenerating_scenario_1_in_place_is_refused():
    run = subprocess.run([sys.executable, str(DATA / "gen_scenario.py")], capture_output=True, text=True,
                         check=False)
    assert run.returncode != 0 and "frozen" in run.stderr
