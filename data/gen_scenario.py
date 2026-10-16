#!/usr/bin/env python3
"""Generate Scenario 1 ("Six Weeks After", Queens) per the Relay Data Spec.

    python data/load_311.py && python data/gen_scenario.py      # -> data/scenarios/s1/

Location privacy: synthetic households live only on clearly fictional streets (config/fictional_streets.json,
checked against NYC's street centerline and all 311 data) and carry one coarse ZIP-level coordinate. Real 311
rows keep their real addresses and coordinates and are never linked to a synthetic person.

Structure first, words second: every household gets a truth timeline built from a closed set of
facts; synthetic events are emitted from those facts (some facts are deliberately never reported),
with name and address variants so entity resolution is really tested. Real 311 records are merged
on the same clock unmodified. Deterministic for a fixed SEED.

Internally everything is in days since storm start; files are written in the contract shape
(`schemas.py`: hours since day 0, events keyed by `_id` with run_id "scenario") by data/contract.py.

Visible to Relay:   events.jsonl (strip `origin`), registry.json
Hidden:             households_truth.json, personas.json, needles.json, decoys.json,
                    promises.json, event_truth.json (event -> household + structured fact)
Human review:       REVIEW.md
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import contract
from addresses import is_real_address, normalize_address

SEED = 21
SCENARIO_ID = "s1"
T_CAL = datetime(2021, 9, 1)      # noqa: DTZ001 - New York wall-clock time, like the 311 timestamps
# calendar day 0 above is a Wednesday
T0 = datetime(2021, 9, 1, 20, 0)  # noqa: DTZ001 - storm start (NY wall clock); internal ts = days since T0
DAYS = 43
N_HOUSEHOLDS = 150
N_REGISTRY = 60
REAL_SHARE = 0.70                 # spec: ~70% real 311 background, ~30% synthetic
LABEL = "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."
CALLBACK = "+1-555-0100"
FACTS = {"power_out", "power_restored", "heat_out", "heat_restored", "flooded", "repaired", "promise",
         "promise_kept", "promise_broken", "stops_answering_until", "answers_again", "needs_supplies",
         "supplies_received", "fine"}

HERE = Path(__file__).parent
DERIVED = HERE / "derived"
OUT = HERE / "scenarios" / SCENARIO_ID
FICTIONAL = json.loads((HERE / "config" / "fictional_streets.json").read_text())["names"]
HERO_STREET = normalize_address(FICTIONAL[0])  # "HOLLOW OAK LN"
STREETS_PER_ZIP = 3
GEO_DECIMALS = 2  # ~1 km: a synthetic person gets a ZIP-level point, never a property-level one

CITY = {"11354": "Flushing", "11355": "Flushing", "11358": "Flushing", "11368": "Corona",
        "11369": "East Elmhurst", "11370": "East Elmhurst", "11372": "Jackson Heights", "11373": "Elmhurst",
        "11375": "Forest Hills", "11377": "Woodside", "11432": "Jamaica", "11104": "Sunnyside"}
LANG_MIX = {  # rough neighborhood texture, not census
    "11354": {"zh": 5, "ko": 3, "en": 1, "es": 1}, "11355": {"zh": 5, "ko": 2, "en": 1, "es": 1},
    "11358": {"ko": 4, "zh": 3, "en": 2}, "11368": {"es": 6, "zh": 1, "bn": 1, "en": 1},
    "11369": {"es": 5, "en": 2, "bn": 1}, "11370": {"es": 4, "en": 2, "bn": 1},
    "11372": {"es": 4, "bn": 3, "en": 2, "zh": 1}, "11373": {"es": 3, "zh": 3, "bn": 2, "en": 2},
    "11375": {"en": 6, "es": 1, "zh": 1}, "11377": {"es": 3, "en": 3, "ko": 1, "bn": 2},
    "11432": {"bn": 4, "en": 3, "es": 2},
}
LANGUAGE_NAME = {"en": "English", "es": "Spanish", "zh": "Mandarin Chinese", "ko": "Korean", "bn": "Bengali"}

F, M = "F", "M"
NAME_POOLS = {
    "zh": [(["Chen", "Wang", "Li", "Zhang", "Liu", "Lin", "Huang", "Wu", "Zhou", "Zheng"],
            [("Mei", F), ("Wei", M), ("Jian", M), ("Xiu Ying", F), ("Hong", F), ("Li Na", F),
             ("Guo Hua", M), ("Yan", F), ("Ming", M), ("Shu Fen", F)])],
    "ko": [(["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon"],
            [("Soon-ja", F), ("Min-ho", M), ("Young-hee", F), ("Jae-sung", M), ("Mi-kyung", F),
             ("Sang-woo", M), ("Kyung-ja", F)])],
    "es": [(["Rodriguez", "Gonzalez", "Martinez", "Vargas", "Morales", "Ramirez", "Castillo",
             "Ortiz", "Hernandez", "Guzman", "Delgado", "Reyes"],
            [("Carmen", F), ("Luis", M), ("Rosa", F), ("Jorge", M), ("Maria", F), ("Ana", F),
             ("Hector", M), ("Jose", M), ("Gloria", F), ("Wilson", M), ("Marisol", F), ("Edgar", M)])],
    "bn": [(["Rahman", "Hossain", "Ahmed", "Islam", "Chowdhury", "Uddin", "Begum", "Miah"],
            [("Abdul", M), ("Rokeya", F), ("Nasima", F), ("Karim", M), ("Fatema", F), ("Jamal", M),
             ("Shahana", F), ("Rafiq", M)])],
    "en": [(["O'Brien", "Murphy", "Russo", "Papadopoulos", "Johnson", "Williams", "Kowalski"],
            [("Mary", F), ("James", M), ("Helen", F), ("George", M), ("Patricia", F), ("Robert", M),
             ("Linda", F), ("Frank", M)]),
           (["Santos", "Cruz", "Reyes", "Bautista"],
            [("Ramon", M), ("Imelda", F), ("Jocelyn", F), ("Rogelio", M)]),
           (["Gurung", "Sherpa", "Tamang", "Shrestha"],
            [("Pemba", M), ("Dawa", F), ("Sita", F), ("Ram", M)]),
           (["Singh", "Patel", "Sharma"], [("Harpreet", F), ("Gurdeep", M), ("Anil", M), ("Priya", F)])],
}
SURNAME_VARIANTS = {
    "Rodriguez": ["Rodrigez", "Rodríguez"], "Gonzalez": ["Gonzales", "González"],
    "Martinez": ["Martínez", "Martines"], "Hernandez": ["Hernández", "Hernandes"],
    "Ramirez": ["Ramírez"], "Castillo": ["Castilo"], "Vargas": ["Vargaz"], "Guzman": ["Guzmán"],
    "Hossain": ["Hussain", "Hossein"], "Chowdhury": ["Choudhury"], "Rahman": ["Rehman"],
    "Ahmed": ["Ahmad"], "Choi": ["Choe"], "Chen": ["Chan", "Chenn"], "Zhang": ["Chang"], "Zheng": ["Cheng"],
    "Wang": ["Wong"], "Lin": ["Lim"], "Papadopoulos": ["Papadopolous"], "O'Brien": ["OBrien"],
    "Murphy": ["Murphey"], "Kowalski": ["Kowalsky"], "Shrestha": ["Shresta"], "Lee": ["Yi"],
}
SHORT_SUFFIX = {"AVE": "Ave", "ST": "St", "RD": "Rd", "PL": "Pl", "BLVD": "Blvd", "DR": "Dr", "LN": "Ln",
                "CT": "Ct", "TER": "Ter"}
LONG_SUFFIX = {"AVE": "Avenue", "ST": "Street", "RD": "Road", "PL": "Place", "BLVD": "Boulevard",
               "DR": "Drive", "LN": "Lane", "CT": "Court", "TER": "Terrace"}
VOLUNTEERS = ["Dana R.", "Marcus T.", "Priya S.", "Kevin L.", "Alma G.", "Tomás V.", "Grace H.", "Omar F."]
CASEWORKER = "Caseworker J. Alvarez"
CONTACT_NAMES = {"zh": ["Wei", "Jun", "Lily"], "ko": ["Daniel", "Min-ji", "Sung"], "es": ["Carlos", "Ana", "Luis"],
                 "bn": ["Rafi", "Tania", "Imran"], "en": ["Mike", "Karen", "Sam"]}

PERSONA_PROMPT = """You are {name}, a fictional resident in a post-storm simulation. Speak {language}.
It is simulated day {{current_day}}. Everything true about your situation up to today:
{{timeline_facts}}
Rules:
- Only know what is true up to today. Never mention future events.
- If your timeline says you are not answering today, output {{"answered": false}}.
- Answer briefly and naturally; you may be vague or confused sometimes, but never contradict your facts.
- If a fact says you fell or are in danger, say so plainly.
Output JSON: {{"answered": true|false, "utterances": ["..."], "facts_disclosed": ["fact ids"]}}"""

rng = random.Random(SEED)


# ---------- time ----------

def at(cal_day, hour=None):
    """Calendar day (0 = Wed Sep 1) + local hour -> ts (days since storm start, Sep 1 20:00)."""
    hour = rng.uniform(8.5, 18.5) if hour is None else hour
    return round(cal_day + hour / 24 - 20 / 24, 4)


def iso(ts):
    return (T0 + timedelta(days=ts)).isoformat(timespec="minutes")


def weekday(cal_day):
    return (T_CAL + timedelta(days=cal_day)).strftime("%A")


def md(cal_day):
    d = T_CAL + timedelta(days=cal_day)
    return f"{d.strftime('%b')} {d.day}"


def next_weekday(cal_day, name):
    d = cal_day + 1
    while weekday(d) != name:
        d += 1
    return d


# ---------- addresses ----------

def ordinal(n):
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def street_forms(norm):
    toks = norm.split()
    return {"short": " ".join(ordinal(t) if t.isdigit() else SHORT_SUFFIX.get(t, t.title()) for t in toks),
            "long": " ".join(ordinal(t) if t.isdigit() else LONG_SUFFIX.get(t, t.title()) for t in toks),
            "plain": " ".join(t if t.isdigit() else SHORT_SUFFIX.get(t, t.title()) for t in toks),
            "upper": " ".join(LONG_SUFFIX.get(t, t).upper() for t in toks),
            "norm": norm}


def floor_phrase(unit):
    if unit == "Bsmt":
        return "basement"
    return f"{ordinal(unit[0])} floor" + (" rear" if unit.endswith("R") else "")


def address_variants(house, street, unit):
    s = street_forms(street)
    compact = house.replace("-", "")
    if unit == "Bsmt":
        u = {"pretty": " Bsmt", "apt": " basement", "311": " BSMT", "crew": " BSMT"}
    elif unit:
        u = {"pretty": f" Apt {unit}", "apt": f" #{unit}", "311": f" APT {unit}", "crew": f" #{unit}"}
    else:
        u = {k: "" for k in ("pretty", "apt", "311", "crew")}
    return {
        "visit": [f"{house} {s['short']}{u['pretty']}", f"{compact} {s['plain']}{u['apt']}",
                  f"{house} {s['long']}", f"{house} {s['short']}"]
                 + ([f"{s['short']}, {floor_phrase(unit)}"] if unit else []),
        "311": [f"{house} {s['upper']}{u['311']}", f"{house} {s['upper']}", f"{compact} {s['upper']}"],
        "crew": [f"{house} {s['norm']}{u['crew']}", f"{house} {s['norm']}"],
    }


def block_label(zip_, street, prefix):
    return f"{street_forms(street)['short']}, {prefix}-01 to {prefix}-99, {CITY.get(zip_, 'Queens')} {zip_}"


# ---------- world ----------

class World:
    def __init__(self, zip_geo):
        self.zip_geo = zip_geo
        self.events, self.event_truth = [], {}
        self.households, self.registry, self.needles, self.decoys = [], [], [], []
        self.used_addresses, self.used_names, self.blocks = set(), set(), {}

    def emit(self, source, ts, text, *, hh=None, address_raw=None, ref=None, author=None, geo=None,
             fact=None, language="en"):
        assert source in {"311", "visit_note", "utility", "crew", "call"}, source
        tmp = f"syn-{len(self.events) + 1:05d}"
        self.events.append({
            "tmp_id": tmp, "ts": round(ts, 4), "ts_real": iso(ts), "source": source,
            "text": re.sub(r"\s+", " ", text).strip(), "address_raw": address_raw,
            "geo": geo or (hh["_geo"] if hh else None), "household_ref_raw": ref,
            "channel_meta": {"author": author, "language": language}, "real_311_key": None,
            "origin": "synthetic",
        })
        self.event_truth[tmp] = {"household_id": hh["household_id"] if hh else None, "fact": fact}
        return tmp

    def fact(self, hh, ts, name, **kw):
        assert name in FACTS, name
        tl = hh["timeline"]
        entry = {"fid": f"f{len(tl) + 1:02d}", "day": round(ts, 3), "fact": name, **kw}
        tl.append(entry)
        return entry

    def promise(self, hh, ts, who, what, due, event_id, kept_at=None, evidence=None):
        pid = f"p{sum(1 for f in hh['timeline'] if f['fact'] == 'promise') + 1}"
        self.fact(hh, ts, "promise", id=pid, who=who, what=what, due_day=round(due, 3), event_id=event_id)
        if kept_at is None:
            self.fact(hh, due, "promise_broken", id=pid)
        else:
            self.fact(hh, kept_at, "promise_kept", id=pid, event_id=evidence)
        return pid


def coarse(lat, lng):
    return {"lat": round(lat, GEO_DECIMALS), "lng": round(lng, GEO_DECIMALS)}


def load_backbone():
    """Real 311 backbone -> fictional street texture.

    Each scenario ZIP gets STREETS_PER_ZIP fictional streets. Fictional street k inherits the flood intensity,
    recovery load and house-number ranges of the ZIP's k-th most flood-hit real street, never its name or
    location (the real name is dropped here). Synthetic coordinates are one coarse point per ZIP.
    """
    intensity = json.loads((DERIVED / "street_intensity.json").read_text())
    prefixes, zip_pts, real = defaultdict(set), defaultdict(list), []
    with (DERIVED / "events_311.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            real.append(e)
            if e["geo"]:
                zip_pts[e["_zip"]].append(e["geo"])
            m = re.match(r"^(\d+)-(\d+)[A-Z]? (.+)$", e["_address_norm"] or "")
            if m and m.group(3) == e["_street"]:
                prefixes[(e["_zip"], e["_street"])].add(int(m.group(1)))
    zip_geo = {z: coarse(sum(p["lat"] for p in v) / len(v), sum(p["lng"] for p in v) / len(v))
               for z, v in sorted(zip_pts.items())}
    zip_geo["11104"] = coarse(40.74, -73.92)  # the hero's ZIP is outside the 311 pull
    skip = {"SR", "EXPY", "HWY", "ENT", "EXIT", "SERVICE", "RAMP", "BRIDGE", "PKWY"}
    names = iter(FICTIONAL[1:1 + STREETS_PER_ZIP * len(LANG_MIX)])
    streets, fictional_prefixes = [], {}
    for zip_ in sorted(LANG_MIX):
        top = [s for s in intensity["streets"] if s["zip"] == zip_
               and len(prefixes[(zip_, s["street"])]) >= 2 and not skip & set(s["street"].split())]
        for s in top[:STREETS_PER_ZIP]:
            name = normalize_address(next(names))
            streets.append({"zip": zip_, "street": name, "flood_intensity": s["flood_intensity"],
                            "recovery_load": s["recovery_load"]})
            fictional_prefixes[(zip_, name)] = prefixes[(zip_, s["street"])]
    return streets, fictional_prefixes, zip_geo, real


def make_household(w, *, zip_, street, prefix, lang=None, sex=None, given=None, family=None, age=None,
                   basement=None, unit=None, lives_alone=None, size=None, house=None, geo=None,
                   reason=None, contacts=None, shared_building=False):
    lang = lang or rng.choices(list(LANG_MIX[zip_]), weights=list(LANG_MIX[zip_].values()))[0]
    families, givens = rng.choice(NAME_POOLS[lang])
    fixed_given, fixed_family = given, family
    for _ in range(100):  # full names are unique: a namesake is a deliberate trap, never an accident
        if fixed_given is None:
            given, sex = rng.choice([g for g in givens if sex is None or g[1] == sex])
        family = fixed_family or rng.choice(families)
        if f"{given} {family}" not in w.used_names:
            break
    else:
        raise RuntimeError(f"no unused name for {fixed_given} {fixed_family}")
    w.used_names.add(f"{given} {family}")
    sex = sex or rng.choice([F, M])
    if house is None:
        for _ in range(300):
            house = f"{prefix}-{rng.randint(1, 99):02d}"
            if f"{house} {street}" not in w.used_addresses and not is_real_address(f"{house} {street}"):
                break
        else:
            raise RuntimeError(f"no free synthetic address on {street} {zip_}")
    w.used_addresses.add(f"{house} {street}")
    age = age or rng.choice([rng.randint(28, 64), rng.randint(65, 79), rng.randint(80, 93)])
    if lives_alone is None:
        lives_alone = age >= 65 and rng.random() < 0.45
    size = 1 if lives_alone else (size or rng.randint(2, 6))
    if basement is None:
        basement = rng.random() < 0.3
    if unit is None:
        unit = "Bsmt" if basement else rng.choice([None, None, "1F", "2F", "2R", "3F", "3R"])

    title = "Mrs." if sex == F else "Mr."
    variants = [f"{given} {family}", f"{title} {family}"]
    variants.append(f"{family} {given}" if lang in ("zh", "ko") else f"{given[0]}. {family}")
    if family in SURNAME_VARIANTS:
        variants.append(f"{given} {rng.choice(SURNAME_VARIANTS[family])}")
    who = ("elderly woman" if sex == F else "older man") if age >= 70 else ("lady" if sex == F else "man")
    variants.append(f"the {who} in {unit}" if unit and unit != "Bsmt" else
                    f"the {who} in the basement" if unit else f"the {who} at {house}")

    members = [{"age": age, "lives_alone": lives_alone}]
    if not lives_alone:
        members += [{"age": rng.randint(1, 17) if i >= 2 and rng.random() < 0.6 else rng.randint(25, 70)}
                    for i in range(1, size)]
    if reason is None:
        bits = (["lives alone"] if lives_alone else []) + (["age 80+"] if age >= 80 else []) \
               + (["basement unit"] if unit == "Bsmt" else []) + (["limited mobility"] if age >= 85 else [])
        reason = "; ".join(bits) or "flood-affected household"
    if contacts is None:
        contacts = [{"relation": rng.choice(["son", "daughter", "niece", "neighbor"]),
                     "name": rng.choice(CONTACT_NAMES[lang])} for _ in range(rng.choice([0, 1, 1, 2]))]
    avs = address_variants(house, street, unit)
    hh = {
        "household_id": f"s1_h_{len(w.households) + 1:03d}", "scenario_id": SCENARIO_ID,
        "canonical_name": f"{given} {family}", "name_variants": variants,
        "address": {"number": house, "street": street_forms(street)["short"], "unit": unit, "zip": zip_,
                    "city": CITY[zip_], "synthetic_number": True},
        "address_variants": sorted({v for vs in avs.values() for v in vs}),
        "members": members, "language": lang, "registry_reason": reason, "contacts": contacts,
        "story": "background", "timeline": [],
        # generator-only (stripped on write)
        "_given": given, "_family": family, "_sex": sex, "_street": street, "_prefix": prefix, "_zip": zip_,
        "_avs": avs, "_geo": geo or w.zip_geo[zip_], "_shared": shared_building,
    }
    w.households.append(hh)
    return hh


def ref(hh, source):
    """(text used for the person, household_ref_raw) as this source would write it."""
    v = hh["name_variants"]
    if source == "311":
        if rng.random() < 0.4:
            return None, None
        name = rng.choice([v[0], v[2]] + v[3:4]).upper()
        return name, name
    if source == "crew":
        if rng.random() < 0.5:
            return None, None
        return v[1], v[1]
    pick = rng.choice([v[1], v[1], v[0], hh["_given"]] + v[3:])
    return pick, pick


def addr(hh, source):
    return rng.choice(hh["_avs"]["visit" if source == "visit_note" else source])


def identity_address(hh):
    """The one address a registration form records for this household.

    W2's matcher compares normalized strings exactly (case, spaces, '-' and '#' ignored), so the unit is part
    of the identity only when another household shares the building (the namesake traps).
    """
    a = hh["address"]
    unit = f" {a['unit']}" if hh["_shared"] and a["unit"] else ""
    return f"{a['number']} {a['street']}{unit}"


def addr_exact(hh, source):
    """An address as `source` would write it that still normalizes to identity_address(hh)."""
    a, s = hh["address"], street_forms(hh["_street"])
    number = a["number"] if source == "crew" else rng.choice([a["number"], a["number"].replace("-", "")])
    unit = a["unit"] if hh["_shared"] and a["unit"] else ""
    if source == "visit_note":
        return f"{number} {s['short']}" + (f" {unit}" if unit else "")
    return f"{number} {s['norm']}" + (f" {unit.upper()}" if unit else "")


def who_desc(hh):
    age, alone, size = hh["members"][0]["age"], hh["members"][0]["lives_alone"], len(hh["members"])
    if age >= 65:
        return f"{'Elderly' if age >= 75 else 'Senior'} resident{', lives alone' if alone else ''}."
    return f"Family of {size}." if size >= 4 else ""


def them(hh):
    return "her" if hh["_sex"] == F else "him"


def register(w, hh, ts, by="self", note=None):
    w.registry.append({"household_id": hh["household_id"], "scenario_id": SCENARIO_ID, "opt_in": True,
                       "language": hh["language"], "callback_number": CALLBACK, "registered_day": round(ts, 3),
                       "name": hh["canonical_name"], "address": identity_address(hh),
                       "registered_by": by, "note": note})


# ---------- outages (utility feed: block level, no names) ----------

def outage(w, zip_, street, prefix, flood_intensity, *, restore_cal=None, push_cal=None, force=False):
    key = (zip_, street, prefix)
    if key in w.blocks and (w.blocks[key] or not force):
        return w.blocks[key]
    heavy = flood_intensity >= 0.35
    if not force and rng.random() > 0.3 + 0.6 * flood_intensity:
        w.blocks[key] = None
        return None
    if restore_cal is None:
        restore_cal = rng.uniform(9.5, 16) if heavy else rng.uniform(1.2, 5)
    label, customers = block_label(zip_, street, prefix), rng.randint(12, 140)
    geo = w.zip_geo.get(zip_)
    start = at(0, rng.uniform(20.5, 23.8))
    first_eta = min(restore_cal, rng.uniform(2.5, 4.5)) if heavy else restore_cal
    kw = {"address_raw": label, "author": "Con Edison", "geo": geo}
    ids = [w.emit("utility", start, f"Con Edison outage update: {customers} customers without power on {label}. "
                  f"Cause: flooding. Estimated restoration: {md(int(first_eta))}.",
                  fact={"block": list(key), "fact": "power_out"}, **kw)]
    if heavy:
        push = push_cal if push_cal is not None else int(first_eta) + rng.choice([0, 1])
        ids.append(w.emit("utility", at(push, rng.uniform(9, 17)),
                          f"Con Edison outage update: restoration on {label} delayed. Flooded equipment in "
                          f"multiple buildings. New estimate: {md(int(restore_cal))} or later.",
                          fact={"block": list(key), "fact": "eta_delayed"}, **kw))
    restore_ts = at(int(restore_cal), (restore_cal % 1) * 24)
    if restore_ts < DAYS:
        ids.append(w.emit("utility", restore_ts,
                          f"Con Edison: service restored on {label}. Buildings with flooded meters or electrical "
                          f"panels need a licensed electrician's certification before reconnection.",
                          fact={"block": list(key), "fact": "power_restored"}, **kw))
    w.blocks[key] = {"zip": zip_, "street": street, "prefix": prefix, "basement_heavy": heavy,
                     "customers": customers, "start": start, "restore_ts": restore_ts, "event_ids": ids}
    return w.blocks[key]


# ---------- background households ----------

INITIAL = [  # (source, template, facts)
    ("311", "Sewer backup in basement, about {ft} of water. {who}", ["flooded"]),
    ("311", "Water in basement after the storm, no power. {who}", ["flooded"]),
    ("311", "No heat and no hot water since the flood. {who}", ["heat_out"]),
    ("311", "Flood debris piled on sidewalk, needs bulk pickup.", ["flooded"]),
    ("311", "Tree came down on the front steps, partly blocking the door. {who}", []),
    ("visit_note", "Visited {name} at {addr}. Basement took water, they're pumping it out. {who}", ["flooded"]),
    ("visit_note", "Stopped by {addr}. {name} says power is out and the fridge is gone. {who}", []),
    ("visit_note", "Checked on {name}, {addr}. Some water in the cellar, mostly OK. {who}", ["flooded"]),
]
PROMISES = [  # (who, what, visit sentence, evidence source, evidence template, due kind, side facts)
    ("daughter", "pick {them} up to stay with family", "Daughter is picking {them} up {when} to stay with family.",
     "visit_note", "Went by {addr}: neighbor says {name}'s daughter picked {them} up, house is empty.", "weekday", []),
    ("DSNY", "bulk pickup of flood debris", "Sanitation says bulk pickup of the flood debris is scheduled {when}.",
     "crew", "DSNY crew: flood debris removed at {addr}.", "weekday", ["repaired"]),
    ("landlord", "send a licensed plumber", "Landlord told them a plumber is coming {when}.",
     "crew", "HPD reinspection at {addr}: plumbing repaired, condition corrected.", "weekday", ["repaired"]),
    ("Red Cross", "deliver water and supplies", "Red Cross will drop off water and cleaning supplies {when}.",
     "crew", "Red Cross ERV: delivered water, cleanup kit, and meals to {addr}.", "tomorrow", ["supplies"]),
    ("FEMA", "home inspection", "FEMA inspection is set for {when}.",
     "visit_note", "FEMA inspection completed at {addr}. Claim moving forward.", "date", []),
    ("caseworker", "call back about temporary housing", ("Caseworker will call {them} back {when} about temporary "
     "housing."), "visit_note", "Called back {name} re: temporary housing; options sent by text.", "weekday", []),
]
STATUS = ["Cleanup going OK.", "Still airing out the basement.", "Power's back, fridge still dead.",
          "Walls drying, some mold starting.", "Neighbors helping with cleanup."]


def background_story(w, hh, flood_intensity):
    block = outage(w, hh["_zip"], hh["_street"], hh["_prefix"], flood_intensity)
    if block:
        w.fact(hh, block["start"], "power_out")
        restore = block["restore_ts"] + (rng.uniform(1, 4) if hh["address"]["unit"] == "Bsmt"
                                         and rng.random() < 0.4 else 0)
        if restore < DAYS:
            w.fact(hh, restore, "power_restored")

    d0 = min(int(rng.expovariate(0.6)), 5) + 1  # calendar day of first report
    source, tpl, facts = rng.choice(INITIAL)
    for f in facts:
        w.fact(hh, at(0, 22.5), f)
    if source == "311":
        name, r = ref(hh, "311")
        a = addr(hh, "311")
        text = (f"311 call from {name} at {a}: " if name else f"311 call re: {a}: ") + tpl.format(
            ft=rng.choice(["a foot", "2 feet", "3 feet"]), who=who_desc(hh))
        w.emit("311", at(d0), text, hh=hh, address_raw=a, ref=r, author="311",
               fact={"facts": facts, "kind": "initial_report"})
    else:
        name, r = ref(hh, "visit_note")
        a = addr(hh, "visit_note")
        w.emit("visit_note", at(d0), tpl.format(name=name, addr=a, who=who_desc(hh)), hh=hh,
               address_raw=a, ref=r, author=f"Volunteer {rng.choice(VOLUNTEERS)}",
               fact={"facts": facts, "kind": "initial_report"})
    if "heat_out" in facts:
        w.fact(hh, at(rng.randint(4, 9)), "heat_restored")

    if rng.random() < 0.65:
        d1 = min(d0 + rng.randint(1, 8), DAYS - 7)
        name, r = ref(hh, "visit_note")
        a = addr(hh, "visit_note")
        vol = f"Volunteer {rng.choice(VOLUNTEERS)}"
        status = rng.choice(STATUS)
        if rng.random() < 0.3:
            w.emit("visit_note", at(d1), f"Checked on {name} at {a}. {status}", hh=hh, address_raw=a, ref=r,
                   author=vol, fact={"kind": "status"})
        else:
            who, what, ptpl, ev_source, ev_tpl, due_kind, side = rng.choice(PROMISES)
            if due_kind == "tomorrow":
                due_cal, when = d1 + 1, "tomorrow"
            elif due_kind == "date":
                due_cal = d1 + rng.randint(4, 9)
                when = md(due_cal)
            else:
                due_cal = d1 + rng.randint(2, 6)
                when = weekday(due_cal)
            author = CASEWORKER if who in ("caseworker", "FEMA") else vol
            ts_note = at(d1)
            note = w.emit("visit_note", ts_note, f"{name}, {a}. {status} " + ptpl.format(them=them(hh), when=when),
                          hh=hh, address_raw=a, ref=r, author=author, fact={"kind": "promise", "who": who})
            due = at(due_cal, 20.0)
            kept_at = (due - rng.uniform(0.1, 1.2)) if rng.random() < 0.85 else (due + rng.uniform(0.25, 1.6))
            kept_at = round(max(kept_at, ts_note + 0.1), 4)
            ev_name, ev_ref = ref(hh, "visit_note")
            ev_addr = addr(hh, ev_source)
            ev = w.emit(ev_source, kept_at, ev_tpl.format(addr=ev_addr, name=ev_name, them=them(hh)),
                        hh=hh, address_raw=ev_addr, ref=ev_ref if "{name}" in ev_tpl else None,
                        author={"crew": "Crew"}.get(ev_source, author), fact={"kind": "promise_kept", "who": who})
            if "supplies" in side:
                w.fact(hh, ts_note, "needs_supplies", what="water and cleanup supplies")
            w.promise(hh, ts_note, who, what.format(them=them(hh)), due, note, kept_at=kept_at, evidence=ev)
            if "supplies" in side:
                w.fact(hh, kept_at, "supplies_received")
            if "repaired" in side:
                w.fact(hh, kept_at, "repaired")
    w.fact(hh, at(rng.randint(18, 30)), "fine")


# ---------- needles and decoys ----------

def needle(w, nid, kind, hh, required, deadline, danger, response_hours, summary):
    hh["story"] = f"needle:{nid}"
    w.needles.append({"needle_id": nid, "scenario_id": SCENARIO_ID, "household_id": hh["household_id"],
                      "kind": kind, "required_event_ids": required, "deadline_day": round(deadline, 3),
                      "danger_day": round(danger, 3), "response_hours": response_hours,
                      "people_at_risk": len(hh["members"]), "summary": summary})


def decoy(w, did, kind, hh, event_ids, reason, resolution):
    """`resolution`: the visible events after which the alarm is resolved (the decoy's own event for namesakes)."""
    hh["story"] = f"decoy:{did}"
    w.decoys.append({"decoy_id": did, "scenario_id": SCENARIO_ID, "household_id": hh["household_id"],
                     "kind": kind, "event_ids": event_ids, "resolution_event_ids": resolution, "reason": reason})


def build_needles_and_decoys(w, streets, prefixes):
    def spot(zip_, rank=0):
        cands = [s for s in streets if s["zip"] == zip_]
        s = cands[min(rank, len(cands) - 1)]
        return s, rng.choice(sorted(prefixes[(zip_, s["street"])]))

    def hh_at(zip_, rank=0, **kw):
        s, p = spot(zip_, rank)
        return make_household(w, zip_=zip_, street=s["street"], prefix=p, **kw), s, p

    # s1_n_01 (hero) Mrs. Chen: son promised Tuesday, never came; block restoration pushed to Sep 13+ on
    # Wednesday; flooded meter keeps her dark; stops answering Wed Sep 8 until Sep 22; answers then.
    hh = make_household(w, zip_="11104", street=HERO_STREET, prefix=41, lang="zh", sex=F, given="Mei", family="Chen",
                        age=82, basement=True, unit="Bsmt", lives_alone=True, house="41-22",
                        reason="lives alone; age 80+; basement unit",
                        contacts=[{"relation": "son", "name": "Wei"}])
    block = outage(w, "11104", HERO_STREET, 41, 0.9, restore_cal=12.6, push_cal=7, force=True)
    visit = w.emit("visit_note", at(2, 14.6),
                   "Visited Mrs. Chen, 82, at 41-22 Hollow Oak Lane. Lives alone, speaks mostly Mandarin. Basement flooded, "
                   "no power since Wednesday night. Her son Wei is coming Tuesday to help clean out and take her to "
                   "stay with him. Registered her for follow-up calls. Follow up Wednesday.",
                   hh=hh, address_raw="41-22 Hollow Oak Ln", ref="Mrs. Chen", author="Volunteer Dana R.",
                   fact={"kind": "promise", "who": "son Wei"})
    register(w, hh, at(2, 15.0), by="volunteer (with consent)", note="Prefers Mandarin.")
    meter = w.emit("crew", at(13, 11.0), "Con Edison field crew: 4122 HOLLOW OAK LN meter room flooded, service not "
                   "reconnected. Needs licensed electrician certification. No one answered the door.",
                   hh=hh, address_raw="4122 HOLLOW OAK LN", author="Con Edison field crew",
                   fact={"kind": "meter_flooded"})
    w.fact(hh, block["start"], "flooded")
    w.fact(hh, block["start"], "power_out")
    w.promise(hh, at(2, 14.6), "son Wei", "come help clean out and take her to stay with him", at(6, 20.0), visit)
    w.fact(hh, at(6, 21.5), "stops_answering_until", until_day=at(21, 9.0), detail="phone dead, no power to charge")
    w.fact(hh, at(19, 12.0), "needs_supplies", what="food and water; running low")
    w.fact(hh, at(21, 9.0), "answers_again", detail="neighbor charged her phone")
    w.fact(hh, at(25, 14.0), "power_restored")
    needle(w, "s1_n_01", "broken_promise", hh, [visit, block["event_ids"][1], meter], at(22, 20), at(25, 20), 24,
           "Son Wei promised Tue Sep 7, never came; block ETA pushed to Sep 13+ on Wed Sep 8; flooded meter keeps "
           "her dark; not answering from the evening of Tue Sep 7 until Wed Sep 22 09:00; answers then.")

    # s1_n_02 oxygen concentrator: Red Cross promised a battery unit Saturday, never delivered.
    hh, s, p = hh_at("11432", 0, lang="bn", sex=M, given="Abdul", family="Rahman", age=74, basement=False,
                     lives_alone=False, size=2, reason="power-dependent medical equipment (oxygen concentrator)",
                     contacts=[{"relation": "daughter", "name": "Tania"}])
    block = outage(w, "11432", s["street"], p, 0.5, restore_cal=8.7, force=True)
    a = addr_exact(hh, "311")
    nm = hh["name_variants"][0].upper()
    call = w.emit("311", at(1, 10.2), f"311 call from daughter of {nm} at {a}: power out since last night, father "
                  f"uses a home oxygen concentrator, backup tank running low.", hh=hh, address_raw=a, ref=nm,
                  author="311", fact={"kind": "needs", "what": "power for oxygen concentrator"})
    a = addr_exact(hh, "visit_note")
    sat = next_weekday(2, "Saturday")
    note = w.emit("visit_note", at(2, 16.0), f"Mr. Rahman, {a}. Red Cross will deliver a portable battery unit "
                  f"Saturday. Daughter staying with him.", hh=hh, address_raw=a, ref="Mr. Rahman", author=CASEWORKER,
                  fact={"kind": "promise", "who": "Red Cross"})
    w.fact(hh, block["start"], "power_out")
    w.fact(hh, at(1, 10.2), "needs_supplies", what="portable battery for oxygen concentrator")
    w.promise(hh, at(2, 16.0), "Red Cross", "deliver portable battery unit", at(sat, 20.0), note)
    w.fact(hh, block["restore_ts"], "power_restored")
    needle(w, "s1_n_02", "broken_promise", hh, [call, note, block["event_ids"][0]], at(4, 20), at(5, 20), 12,
           "Oxygen concentrator user; battery promised Sat Sep 4, never delivered; block out until ~Sep 9.")

    # s1_n_03 landlord promised a plumber Friday; sewage still in a cellar unit with kids.
    hh, s, p = hh_at("11368", 0, lang="es", sex=F, given="Gloria", family="Hernandez", age=34, basement=True,
                     lives_alone=False, size=5, reason="basement unit; 2 children")
    a = addr_exact(hh, "crew")
    hpd = w.emit("crew", at(5, 13.0), f"HPD inspection at {a}, cellar unit (tenant Mrs. Hernandez): sewage on floor, "
                 f"no heat/hot water. Family of 5 incl. 2 children. Landlord states licensed plumber coming Friday.",
                 hh=hh, address_raw=a, ref="Mrs. Hernandez", author="HPD inspector",
                 fact={"kind": "promise", "who": "landlord"})
    fri = next_weekday(5, "Friday")
    w.fact(hh, at(0, 22.5), "flooded")
    w.fact(hh, at(0, 23.0), "heat_out")
    w.promise(hh, at(5, 13.0), "landlord", "send licensed plumber", at(fri, 20.0), hpd)
    nm = hh["name_variants"][3].upper() if len(hh["name_variants"]) > 4 else hh["name_variants"][1].upper()
    a = addr_exact(hh, "311")
    again = w.emit("311", at(12, 19.4), f"311 call from {nm} at {a}: sewage still in apartment, nobody came to fix it, "
                   f"kids sleeping upstairs at neighbor's.", hh=hh, address_raw=a, ref=nm, author="311",
                   fact={"kind": "still_broken"})
    needle(w, "s1_n_03", "broken_promise", hh, [hpd, again], at(14, 20), at(17, 20), 48,
           "Landlord promised plumber Fri Sep 10; sewage still there Sep 13; family of 5 with 2 kids.")

    # s1_n_04 caseworker promised a callback about temporary housing; never called.
    hh, s, p = hh_at("11354", 0, lang="ko", sex=F, given="Soon-ja", family="Kim", age=77, basement=True,
                     lives_alone=True)
    a = addr_exact(hh, "visit_note")
    thu = next_weekday(3, "Thursday")
    note = w.emit("visit_note", at(3, 11.0), f"Mrs. Kim, 77, {a}. Basement unit unlivable, sleeping on a neighbor's "
                  f"couch upstairs. Caseworker will call her back Thursday about temporary housing. Speaks Korean, "
                  f"some English.", hh=hh, address_raw=a, ref="Mrs. Kim", author="Volunteer Grace H.",
                  fact={"kind": "promise", "who": "caseworker"})
    register(w, hh, at(3, 11.5), note="Korean preferred.")
    w.fact(hh, at(0, 22.5), "flooded")
    w.promise(hh, at(3, 11.0), "caseworker", "call back about temporary housing", at(thu, 20.0), note)
    a = addr_exact(hh, "311")
    neighbor = w.emit("311", at(14, 9.0), f"311 call re: {a}: elderly woman staying on my couch since the flood, I'm "
                      f"moving out end of the week, she has nowhere to go.", hh=hh, address_raw=a, author="311",
                      fact={"kind": "needs", "what": "housing"})
    needle(w, "s1_n_04", "broken_promise", hh, [note, neighbor], at(16, 20), at(19, 20), 48,
           "Caseworker callback promised Thu Sep 9 never happened; the neighbor hosting her moves out ~Sep 18.")

    # s1_n_05 cross-service join: wheelchair user alone by day in a dark basement (311 typo name, DEP, visit, utility).
    hh, s, p = hh_at("11369", 0, lang="es", sex=M, given="Luis", family="Rodriguez", age=81, basement=True,
                     lives_alone=False, size=2, reason="wheelchair user; basement unit",
                     contacts=[{"relation": "son", "name": "Jose"}])
    block = outage(w, "11369", s["street"], p, 0.95, restore_cal=14.2, force=True)
    a311 = f"{hh['address']['number'].replace('-', '')} {street_forms(s['street'])['norm']}"  # compact number
    a = w.emit("311", at(1, 0.8), f"311 call from JOSE RODRIGEZ at {a311}: water rising in basement, elderly father "
               f"can't do stairs.", hh=hh, address_raw=a311, ref="JOSE RODRIGEZ", author="311",
               fact={"kind": "vulnerable", "what": "cannot use stairs"})
    ac = addr_exact(hh, "crew")
    b = w.emit("crew", at(3, 15.0), f"DEP crew pumped basement at {ac}. Occupant Mr. Rodriguez uses a wheelchair, "
               f"declined to leave.", hh=hh, address_raw=ac, ref="Mr. Rodriguez", author="DEP crew 7",
               fact={"kind": "vulnerable", "what": "wheelchair"})
    av = addr_exact(hh, "visit_note")
    c = w.emit("visit_note", at(10, 17.5), f"Man in a wheelchair at {av}. Basement unit, alone during the day, son "
               f"works nights. Said he's fine, didn't want help.", hh=hh, address_raw=av, ref="Man in a wheelchair",
               author="Volunteer Omar F.", fact={"kind": "vulnerable", "what": "alone by day"})
    w.fact(hh, at(0, 22.0), "flooded")
    w.fact(hh, block["start"], "power_out")
    w.fact(hh, block["restore_ts"], "power_restored")
    needle(w, "s1_n_05", "cross_service_join", hh, [a, b, c, block["event_ids"][1]], at(12, 20), at(15, 20), 24,
           "Wheelchair user alone by day in a dark basement; visible only when 311 (typo name, compact address), "
           "DEP, a nameless visit note, and the utility delay are joined.")

    # s1_n_06 cross-service join: insulin in a dead fridge; building meter flooded after the block came back.
    hh, s, p = hh_at("11373", 0, lang="bn", sex=F, given="Nasima", family="Hossain", age=69, basement=False,
                     unit="2F", lives_alone=True, reason="lives alone; insulin-dependent")
    a311 = addr_exact(hh, "311")
    a = w.emit("311", at(6, 8.0), f"311 call from N. HUSSAIN at {a311}: no heat, no hot water, no electricity in "
               f"building.", hh=hh, address_raw=a311, ref="N. HUSSAIN", author="311", fact={"kind": "no_power"})
    ac = addr_exact(hh, "crew")
    b = w.emit("crew", at(7, 12.0), f"Con Edison field crew: {ac} building panel flooded; block service restored but "
               f"building not reconnected pending electrician.", hh=hh, address_raw=ac,
               author="Con Edison field crew", fact={"kind": "no_power"})
    av = addr_exact(hh, "visit_note")
    c = w.emit("visit_note", at(8, 14.0), f"Mrs. Hussain at {av}, lives alone. Keeps her insulin in the fridge, fridge "
               f"has been off for days.", hh=hh, address_raw=av, ref="Mrs. Hussain", author="Volunteer Priya S.",
               fact={"kind": "needs", "what": "refrigeration for insulin"})
    w.fact(hh, at(0, 22.0), "power_out")
    w.fact(hh, at(0, 22.0), "heat_out")
    w.fact(hh, at(8, 14.0), "needs_supplies", what="refrigeration for insulin")
    w.fact(hh, at(18, 12.0), "power_restored")
    needle(w, "s1_n_06", "cross_service_join", hh, [a, b, c], at(9, 20), at(12, 8), 24,
           "Building dark (flooded panel) + insulin needs refrigeration; 311, Con Ed crew, and visit under name "
           "variants.")

    # s1_n_07 cross-service join: vacate order on an illegal cellar unit; elderly couple sleeping in a stairwell.
    hh, s, p = hh_at("11373", 1, lang="zh", sex=M, given="Guo Hua", family="Wang", age=84, basement=True,
                     shared_building=True,
                     lives_alone=False, size=2, reason="age 80+; couple; illegal cellar unit")
    wang_house, wang_street, wang_prefix = hh["address"]["number"], s["street"], p
    a311 = addr_exact(hh, "311")
    a = w.emit("311", at(4, 10.0), f"311 complaint at {a311}: illegal conversion, elderly couple (the Wangs) living in "
               f"cellar after flood.", hh=hh, address_raw=a311, ref="the Wangs", author="311",
               fact={"kind": "illegal_unit"})
    ac = addr_exact(hh, "crew")
    b = w.emit("crew", at(6, 11.0), f"DOB: vacate order issued for cellar unit at {ac}. Occupants to relocate.",
               hh=hh, address_raw=ac, author="DOB inspector", fact={"kind": "vacate_order"})
    av = addr_exact(hh, "visit_note")
    c = w.emit("visit_note", at(7, 16.0), f"Older couple, the Wangs, {av}. Had to leave the cellar, sleeping in the "
               f"building's back stairwell. Only speak Mandarin.", hh=hh, address_raw=av, ref="the Wangs",
               author="Volunteer Kevin L.", fact={"kind": "needs", "what": "shelter"})
    w.fact(hh, at(0, 22.0), "flooded")
    w.fact(hh, at(7, 16.0), "needs_supplies", what="shelter; sleeping in stairwell")
    needle(w, "s1_n_07", "cross_service_join", hh, [a, b, c], at(10, 20), at(13, 20), 48,
           "Vacate order + elderly couple sleeping in a stairwell; joined across 311, DOB, volunteer.")

    # s1_n_08..10 silent households: opted in, reported once, then stop answering while the outage persists.
    for nid, zip_, kw, first_cal, text, reg_text in [
        ("s1_n_08", "11377", {"lang": "es", "sex": F, "given": "Carmen", "family": "Morales", "age": 79,
                              "basement": True, "lives_alone": True}, 1,
         "Basement apartment flooded, no power, resident {age} lives alone.",
         ("Registered {ref}, {age}, at {addr} for follow-up calls. Lives alone in the basement unit; no power "
          "since the storm.")),
        ("s1_n_09", "11372", {"lang": "en", "sex": F, "given": "Dawa", "family": "Sherpa", "age": 31,
                              "basement": True, "lives_alone": False, "size": 3, "reason": "basement unit; infant"}, 2,
         "No water pressure and no power in basement unit, family of 3 with an infant.",
         ("Registered {ref} at {addr} for follow-up calls. Family of 3 with an infant in the basement unit; no "
          "water pressure, no power.")),
        ("s1_n_10", "11375", {"lang": "en", "sex": M, "given": "George", "family": "Papadopoulos", "age": 91,
                              "basement": False, "lives_alone": True, "reason": "lives alone; uses a walker",
                              "contacts": [{"relation": "son", "name": "Nick"}]}, 1,
         "Tree down across the front steps, resident {age} uses a walker and can't get out.",
         ("Son Nick registered his father, {ref}, {age}, at {addr} for follow-up calls. Uses a walker; the fallen "
          "tree still blocks the front steps.")),
    ]:
        hh, s, p = hh_at(zip_, 0, **kw)
        nm = hh["name_variants"][0].upper()
        a311 = addr_exact(hh, "311")
        first = w.emit("311", at(first_cal, rng.uniform(7, 12)), f"311 call from {nm} at {a311}: "
                       + text.format(age=hh["members"][0]["age"]), hh=hh, address_raw=a311, ref=nm, author="311",
                       fact={"kind": "initial_report"})
        reg_ts, reg_ref, reg_addr = w.events[-1]["ts"] + 0.05, hh["name_variants"][1], addr_exact(hh, "visit_note")
        reg = w.emit("visit_note", reg_ts, reg_text.format(ref=reg_ref, age=hh["members"][0]["age"], addr=reg_addr),
                     hh=hh, address_raw=reg_addr, ref=reg_ref, author=f"Volunteer {rng.choice(VOLUNTEERS)}",
                     fact={"kind": "registration"})
        register(w, hh, reg_ts, by="family" if nid == "s1_n_10" else "self")
        block = outage(w, zip_, s["street"], p, 0.8, restore_cal=rng.uniform(10, 13), force=True)
        w.fact(hh, block["start"], "power_out")
        if nid != "s1_n_10":
            w.fact(hh, at(0, 22.5), "flooded")
        silent_from, silent_to = at(first_cal + 1, 12), at(first_cal + 11, 12)
        w.fact(hh, silent_from, "stops_answering_until", until_day=silent_to, detail="phone dead / not picking up")
        w.fact(hh, silent_to, "answers_again")
        w.fact(hh, block["restore_ts"], "power_restored")
        needle(w, nid, "silent_household", hh, [first, reg, block["event_ids"][0]], at(first_cal + 6, 20),
               at(first_cal + 9, 20), 24,
               f"Opted in Sep {first_cal + 1}, then stops answering for 10 days while the block stays dark.")

    # ---- decoys ----
    # s1_d_01 restored_outage: "no power", restored next day
    hh, s, p = hh_at("11355", 1, age=72, lives_alone=True)
    name, r = ref(hh, "311")
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(2, 9.0), f"311 call {'from ' + name + ' ' if name else ''}at {a311}: no power since the storm, "
               f"senior lives alone.", hh=hh, address_raw=a311, ref=r, author="311", fact={"kind": "no_power"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(3, 10.0), f"Con Edison field crew: service restored at {ac}.", hh=hh, address_raw=ac,
           author="Con Edison field crew", fact={"kind": "power_restored"})
    w.fact(hh, at(0, 22.0), "power_out")
    w.fact(hh, at(3, 10.0), "power_restored")
    w.fact(hh, at(3, 12.0), "fine")
    decoy(w, "s1_d_01", "restored_outage", hh, [x], "No-power report; restored next day.", [y])

    # s1_d_02 resolved_alarm: "elderly man trapped in basement", evacuated the same night
    hh, s, p = hh_at("11369", 2, sex=M, given="Frank", family="Russo", lang="en", age=86, basement=True)
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(0, 23.1), f"311 call from neighbor at {a311}: elderly man trapped in basement, water rising.",
               hh=hh, address_raw=a311, author="311", fact={"kind": "alarm"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(1, 2.0), f"FDNY: resident at {ac} evacuated safely, staying with daughter in Bayside.",
           hh=hh, address_raw=ac, author="FDNY", fact={"kind": "resolved"})
    w.fact(hh, at(0, 22.5), "flooded")
    w.fact(hh, at(1, 2.0), "fine", detail="evacuated; staying with daughter in Bayside")
    decoy(w, "s1_d_02", "resolved_alarm", hh, [x], "Trapped-in-basement report; evacuated within hours.", [y])

    # s1_d_03 kept_promise: hero mirror. Son came Tuesday.
    hh, s, p = hh_at("11354", 2, sex=F, given="Xiu Ying", family="Liu", lang="zh", age=84, basement=True,
                     lives_alone=True, contacts=[{"relation": "son", "name": "Jun"}])
    av = addr_exact(hh, "visit_note")
    x = w.emit("visit_note", at(2, 11.0), f"Visited Mrs. Liu, 84, {av}. Lives alone, basement flooded, no power. Son "
               f"coming Tuesday to take her to his place.", hh=hh, address_raw=av, ref="Mrs. Liu",
               author="Volunteer Marcus T.", fact={"kind": "promise", "who": "son"})
    register(w, hh, at(2, 11.5), by="volunteer (with consent)")
    av2 = addr_exact(hh, "visit_note")
    y = w.emit("visit_note", at(6, 15.0), f"Back at {av2}: Mrs. Liu's son arrived, packing her things, she's going to "
               f"Fort Lee with him.", hh=hh, address_raw=av2, ref="Mrs. Liu", author="Volunteer Marcus T.",
               fact={"kind": "promise_kept"})
    w.fact(hh, at(0, 22.5), "flooded")
    w.fact(hh, at(0, 22.5), "power_out")
    w.promise(hh, at(2, 11.0), "son Jun", "take her to his place", at(6, 20.0), x, kept_at=at(6, 15.0), evidence=y)
    w.fact(hh, at(6, 17.0), "fine", detail="staying with son in Fort Lee")
    decoy(w, "s1_d_03", "kept_promise", hh, [x], "Hero mirror: son promised Tuesday and came (kept event logged "
          "quietly).", [y])

    # s1_d_04 resolved_alarm: opted in, misses calls for a day, answers the next day and is fine
    hh, s, p = hh_at("11377", 1, sex=F, given="Rosa", family="Delgado", lang="es", age=76, lives_alone=True)
    a311 = addr_exact(hh, "311")
    nm = hh["name_variants"][2].upper()
    x = w.emit("311", at(1, 13.0), f"311 call from {nm} at {a311}: water in basement, senior resident.", hh=hh,
               address_raw=a311, ref=nm, author="311", fact={"kind": "initial_report"})
    register(w, hh, at(1, 14.0))
    av = addr_exact(hh, "visit_note")
    y = w.emit("visit_note", at(5, 11.0), f"Checked on Mrs. Delgado at {av}: basement dried out, she is fine. Missed "
               f"our call yesterday, she was at the laundromat.", hh=hh, address_raw=av, ref="Mrs. Delgado",
               author="Volunteer Alma G.", fact={"kind": "resolved"})
    w.fact(hh, at(0, 22.5), "flooded")
    w.fact(hh, at(4, 9.0), "stops_answering_until", until_day=at(5, 9.0), detail="at the laundromat all day")
    w.fact(hh, at(5, 9.0), "answers_again")
    w.fact(hh, at(5, 9.0), "fine")
    decoy(w, "s1_d_04", "resolved_alarm", hh, [x], "Misses calls for one day, answers the next and is fine.", [y])

    # s1_d_05 resolved_alarm: gas smell, no leak found
    hh, s, p = hh_at("11373", 2, age=45)
    name, r = ref(hh, "311")
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(3, 18.0), f"311 call {'from ' + name + ' ' if name else ''}at {a311}: smell of gas in basement "
               f"after flood.", hh=hh, address_raw=a311, ref=r, author="311", fact={"kind": "alarm"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(3, 20.5), f"Con Edison gas crew at {ac}: no leak found, odor from wet boiler room, cleared.",
           hh=hh, address_raw=ac, author="Con Edison gas crew", fact={"kind": "resolved"})
    w.fact(hh, at(3, 20.5), "fine")
    decoy(w, "s1_d_05", "resolved_alarm", hh, [x], "Gas smell; no leak found the same evening.", [y])

    # s1_d_06 resolved_alarm: sewage with kids, cleared next day, corrected Sep 6
    hh, s, p = hh_at("11368", 1, age=38, lives_alone=False, size=4, basement=True)
    name, r = ref(hh, "311")
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(2, 8.0), f"311 call {'from ' + name + ' ' if name else ''}at {a311}: sewage backing up into "
               f"apartment, 2 kids at home.", hh=hh, address_raw=a311, ref=r, author="311", fact={"kind": "alarm"})
    ac = addr_exact(hh, "crew")
    w.emit("crew", at(3, 10.0), f"DEP crew cleared sewer line at {ac}.", hh=hh, address_raw=ac, author="DEP crew 3",
           fact={"kind": "repaired"})
    y = w.emit("crew", at(5, 14.0), f"HPD reinspection at {ac}: unit cleaned and sanitized by landlord, condition "
           f"corrected.", hh=hh, address_raw=ac, author="HPD inspector", fact={"kind": "repaired"})
    w.fact(hh, at(0, 22.5), "flooded")
    w.fact(hh, at(5, 14.0), "repaired")
    w.fact(hh, at(5, 14.0), "fine")
    decoy(w, "s1_d_06", "resolved_alarm", hh, [x], "Sewage with kids; cleared next day, corrected Sep 6.", [y])

    # s1_d_07 kept_promise: no food, Red Cross delivered within hours
    hh, s, p = hh_at("11432", 1, age=80, lives_alone=True)
    name, r = ref(hh, "visit_note")
    av = addr_exact(hh, "visit_note")
    x = w.emit("visit_note", at(4, 10.0), f"{name}, {av}: no food in the house, fridge spoiled. Red Cross will bring "
               f"meals this afternoon.", hh=hh, address_raw=av, ref=r, author="Volunteer Tomás V.",
               fact={"kind": "promise", "who": "Red Cross"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(4, 15.0), f"Red Cross ERV: delivered meals and water to {ac}.", hh=hh, address_raw=ac,
               author="Red Cross", fact={"kind": "promise_kept"})
    w.fact(hh, at(4, 10.0), "needs_supplies", what="food")
    w.promise(hh, at(4, 10.0), "Red Cross", "bring meals", at(4, 20.0), x, kept_at=at(4, 15.0), evidence=y)
    w.fact(hh, at(4, 15.0), "supplies_received")
    decoy(w, "s1_d_07", "kept_promise", hh, [x], "No food; meals delivered the same afternoon.", [y])

    # s1_d_08 resolved_alarm: neighbor not seen for days; wellness check finds her fine
    hh, s, p = hh_at("11358", 0, sex=F, age=83, lives_alone=True)
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(9, 17.0), f"311 call from neighbor at {a311}: elderly neighbor not seen in days, lights off.",
               hh=hh, address_raw=a311, author="311", fact={"kind": "alarm"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(10, 9.0), f"NYPD wellness check at {ac}: resident fine, was staying with her sister in "
           f"Bayside, now home.", hh=hh, address_raw=ac, author="NYPD 110 Pct", fact={"kind": "resolved"})
    w.fact(hh, at(10, 9.0), "fine")
    decoy(w, "s1_d_08", "resolved_alarm", hh, [x], "Not seen for days; wellness check finds her fine.", [y])

    # s1_d_09 namesake: another Wang in the same building as s1_n_07 (3F, fine). Must not merge with the cellar Wangs.
    hh = make_household(w, zip_="11373", street=wang_street, prefix=wang_prefix, house=wang_house, lang="zh",
                        sex=F, given="Hong", family="Wang", age=58, basement=False, unit="3F", lives_alone=False,
                        size=3, shared_building=True)
    av = addr_exact(hh, "visit_note")
    x = w.emit("visit_note", at(5, 12.0), f"Mrs. Wang, {av}: upstairs unit dry, power back, doing fine, helping "
               f"neighbors.", hh=hh, address_raw=av, ref="Mrs. Wang", author="Volunteer Kevin L.",
               fact={"kind": "status"})
    w.fact(hh, at(5, 12.0), "fine")
    decoy(w, "s1_d_09", "namesake", hh, [x], "Same surname, same building as s1_n_07, different unit (3F); fine.", [x])

    # s1_d_10 + s1_d_11: two Gonzalez households in one building; the 1F one reports no power, restored next day.
    hh, s, p = hh_at("11368", 2, sex=F, given="Maria", family="Gonzalez", lang="es", age=70, basement=False,
                     unit="1F", lives_alone=True, shared_building=True)
    other = make_household(w, zip_="11368", street=s["street"], prefix=p, house=hh["address"]["number"], lang="es",
                           sex=F, given="Ana", family="Gonzalez", age=44, basement=True, lives_alone=False, size=4,
                           shared_building=True)
    a311 = addr_exact(hh, "311")
    x = w.emit("311", at(2, 11.0), f"311 call from MARIA GONZALEZ at {a311}: no power, water in the building.",
               hh=hh, address_raw=a311, ref="MARIA GONZALEZ", author="311", fact={"kind": "no_power"})
    ac = addr_exact(hh, "crew")
    y = w.emit("crew", at(3, 16.0), f"Con Edison field crew: service restored at {ac}, basement pumped by owner.",
           hh=hh, address_raw=ac, author="Con Edison field crew", fact={"kind": "power_restored"})
    av = addr_exact(other, "visit_note")
    z = w.emit("visit_note", at(5, 12.0), f"Mrs. Gonzales at {av}, cleanup done, doing fine.", hh=other,
               address_raw=av, ref="Mrs. Gonzales", author="Volunteer Alma G.", fact={"kind": "status"})
    for h in (hh, other):
        w.fact(h, at(0, 22.0), "power_out")
        w.fact(h, at(3, 16.0), "power_restored")
        w.fact(h, at(5, 12.0), "fine")
    decoy(w, "s1_d_10", "restored_outage", hh, [x], "Maria Gonzalez (1F): no power, restored next day.", [y])
    decoy(w, "s1_d_11", "namesake", other, [z], "Ana Gonzalez (basement), same building as s1_d_10; must not merge.", [z])


# ---------- hidden contact truth (call simulator only) ----------

# What a registered resident says when a call connects: (anchor, text) where the anchor is 0 or the first timeline
# fact of that name. Fixed text, so a baseline run and a Relay run hear exactly the same resident.
SCRIPTS = {
    "needle:s1_n_01": [(0, "My son Wei is coming Tuesday to help. Still no power."),
                       ("promise_broken", "My son did not come on Tuesday. Still no power."),
                       ("answers_again", ("My son never came. The power is still out. I have a little food left, "
                                          "not much."))],
    "needle:s1_n_04": [(0, "I'm staying on my neighbor's couch. The caseworker said she would call Thursday."),
                       ("promise_broken", "Nobody called me about housing. My neighbor is moving out soon.")],
    "needle:s1_n_08": [(0, "Still no power. The basement is still wet."),
                       ("answers_again", "My phone was dead for days. Nobody came.")],
    "needle:s1_n_09": [(0, "No power and no water pressure. The baby is okay for now."),
                       ("answers_again", "My phone was dead for days. Nobody came.")],
    "needle:s1_n_10": [(0, "The tree is still across my steps. I can't get out with my walker."),
                       ("answers_again", "My phone was dead for days. Nobody came.")],
    "decoy:s1_d_03": [(0, "My son is coming Tuesday to take me to his place."),
                      ("promise_kept", "I'm at my son's in Fort Lee now. I'm fine.")],
    "decoy:s1_d_04": [(0, "Water in the basement, but I'm managing."),
                      ("answers_again", "Sorry I missed you, I was at the laundromat. I'm fine.")],
}
DEFAULT_SCRIPT = [(0, "We're managing, thank you for checking."), ("power_restored", "The power is back. We're okay.")]


def contact_truth(w, revision):
    """Registered households only (calls need opt-in): when a call connects and what the resident says."""
    by_id = {h["household_id"]: h for h in w.households}
    out = []
    for entry in w.registry:
        hh = by_id[entry["household_id"]]
        first = {}
        for f in sorted(hh["timeline"], key=lambda f: (f["day"], f["fid"])):
            first.setdefault(f["fact"], f["day"])
        script = []
        for anchor, text in SCRIPTS.get(hh["story"], DEFAULT_SCRIPT):
            if anchor == 0 or anchor in first:
                script.append({"from_ts": 0.0 if anchor == 0 else round(contract.hours(first[anchor]), 1), "text": text})
        no_answer = [{"from_ts": round(contract.hours(f["day"]), 1), "until_ts": round(contract.hours(f["until_day"]), 1),
                      "detail": f.get("detail")}
                     for f in hh["timeline"] if f["fact"] == "stops_answering_until"]
        out.append({"household_id": hh["household_id"], "language": hh["language"],
                    "no_answer": sorted(no_answer, key=lambda i: i["from_ts"]),
                    "script": sorted(script, key=lambda line: line["from_ts"])})
    return {
        "scenario_id": SCENARIO_ID, "revision": revision,
        "visibility": "hidden: call simulator and evaluator only; never runtime decision logic",
        "rule": ("A call at ts connects unless ts falls in a no_answer [from_ts, until_ts) interval. When it "
                 "connects, the resident says the last script line with from_ts <= ts. Call results are written "
                 "by the calling run under its own run_id, never run_id 'scenario'."),
        "households": sorted(out, key=lambda e: e["household_id"]),
    }


# ---------- real 311 texture ----------

def real_texture(real, home_zips, budget):
    pool = [e for e in real if e["_zip"] in home_zips]
    early, later = [e for e in pool if e["_day"] <= 3], [e for e in pool if e["_day"] > 3]
    rng.shuffle(early)
    rng.shuffle(later)
    take = early[:int(budget * 0.4)]
    take += later[:budget - len(take)]
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in take]


# ---------- review ----------

def review_md(w, by_id, households):
    hh_by = {h["household_id"]: h for h in households}
    lines = [f"# Scenario {SCENARIO_ID} review", "", f"_{LABEL}_", "",
             "For every needle: can a person find it from the visible events alone, before the deadline?",
             "h = hours since day 0 (storm start, Sep 1 20:00), as in events.jsonl.", ""]

    def evline(eid, mark=""):
        e = by_id[eid]
        return f"- {mark}`{eid}` h {e['ts'] * 24:.1f} ({e['ts_real'][5:16]}) [{e['source']}] {e['text']}"

    def show_household(hid, marks):
        ids = sorted({eid for eid, t in w.event_truth_final.items() if t["household_id"] == hid} | set(marks),
                     key=lambda i: by_id[i]["ts"])
        return [evline(i, marks.get(i, "")) for i in ids]

    def header(h):
        a = h["address"]
        return f"{h['canonical_name']}, {h['members'][0]['age']} · {a['number']} {a['street']} " \
               f"{a['unit'] or ''}, {a['city']} {a['zip']}"

    lines.append("## Needles")
    for n in w.needles:
        h = hh_by[n["household_id"]]
        lines += ["", f"### {n['needle_id']} · {n['kind']} · {header(h)}", n["summary"] + "  ",
                  (f"**deadline h {n['deadline_day'] * 24:.1f}** · danger h {n['danger_day'] * 24:.1f} · response "
                   f"{n['response_hours']}h · people at risk {n['people_at_risk']} · name variants: "
                   f"{', '.join(h['name_variants'])}"), ""]
        lines += show_household(n["household_id"], {i: "**REQ** " for i in n["required_event_ids"]})
        lines.append("- truth: " + "; ".join(
            f"h {f['day'] * 24:.0f} {f['fact']}" + (f" ({f.get('what') or f.get('who')})" if f.get("what") or f.get("who")
                                             else "") for f in h["timeline"]))
    lines += ["", "## Decoys"]
    for d in w.decoys:
        h = hh_by[d["household_id"]]
        lines += ["", f"### {d['decoy_id']} · {d['kind']} · {header(h)}", d["reason"], ""]
        lines += show_household(d["household_id"], {i: "**DECOY** " for i in d["event_ids"]})
    return "\n".join(lines) + "\n"


# ---------- main ----------

def main(out=OUT):
    streets, prefixes, zip_geo, real = load_backbone()
    w = World(zip_geo)
    build_needles_and_decoys(w, streets, prefixes)

    weights = [0.15 + 2 * s["flood_intensity"] + s["recovery_load"] for s in streets]
    while len(w.households) < N_HOUSEHOLDS:
        s = rng.choices(streets, weights=weights)[0]
        hh = make_household(w, zip_=s["zip"], street=s["street"],
                            prefix=rng.choice(sorted(prefixes[(s["zip"], s["street"])])))
        background_story(w, hh, s["flood_intensity"])

    registered = {r["household_id"] for r in w.registry}
    pool = sorted((h for h in w.households if h["household_id"] not in registered and h["story"] == "background"),
                  key=lambda h: (-h["members"][0]["age"], h["household_id"]))
    for hh in pool[:max(0, N_REGISTRY - len(w.registry))]:
        first = min((e["ts"] for e in w.events if w.event_truth[e["tmp_id"]]["household_id"] == hh["household_id"]),
                    default=at(1))
        register(w, hh, first + 0.05, by=rng.choice(["self", "family"]))

    home = {h["_zip"] for h in w.households}
    real_events = real_texture(real, home, round(len(w.events) * REAL_SHARE / (1 - REAL_SHARE)))

    # merge on one clock, assign final ids in time order, remap every reference
    merged = sorted(w.events + real_events, key=lambda e: (e["ts"], e["tmp_id"]))
    idmap = {e["tmp_id"]: f"{SCENARIO_ID}_e_{i + 1:06d}" for i, e in enumerate(merged)}
    events = [{"event_id": idmap[e["tmp_id"]], "scenario_id": SCENARIO_ID,
               **{k: v for k, v in e.items() if k != "tmp_id"}} for e in merged]
    w.event_truth_final = {idmap[t]: v for t, v in w.event_truth.items()}
    for e in real_events:
        w.event_truth_final[idmap[e["tmp_id"]]] = {"household_id": None, "fact": None}
    w.event_truth_final = dict(sorted(w.event_truth_final.items()))
    for n in w.needles:
        n["required_event_ids"] = [idmap[i] for i in n["required_event_ids"]]
    for d in w.decoys:
        d["event_ids"] = [idmap[i] for i in d["event_ids"]]
        d["resolution_event_ids"] = [idmap[i] for i in d["resolution_event_ids"]]
    for h in w.households:
        for f in h["timeline"]:
            if f.get("event_id"):
                f["event_id"] = idmap[f["event_id"]]
        h["timeline"].sort(key=lambda f: (f["day"], f["fid"]))

    households = [{k: v for k, v in h.items() if not k.startswith("_")} for h in w.households]
    personas = [{"household_id": h["household_id"], "scenario_id": SCENARIO_ID,
                 "persona_prompt": PERSONA_PROMPT.format(name=h["canonical_name"],
                                                         language=LANGUAGE_NAME[h["language"]]),
                 "voice_style": ("slow, polite, a little hard of hearing" if h["members"][0]["age"] >= 80 else
                                 "brief and practical") + ("; worried" if h["story"].startswith("needle") else "")}
                for h in households]
    promises = []
    for h in households:
        for f in h["timeline"]:
            if f["fact"] != "promise":
                continue
            end = next(g for g in h["timeline"] if g["fact"] in ("promise_kept", "promise_broken") and g["id"] == f["id"])
            promises.append({"household_id": h["household_id"], "promise_id": f"{h['household_id']}_{f['id']}",
                             "who": f["who"], "what": f["what"], "made_day": f["day"], "due_day": f["due_day"],
                             "made_in_event_id": f["event_id"], "status": end["fact"].split("_")[1],
                             "resolved_day": end["day"], "evidence_event_id": end.get("event_id")})

    out.mkdir(parents=True, exist_ok=True)
    events_text = "".join(json.dumps(contract.event(e), ensure_ascii=False) + "\n" for e in events)
    revision = hashlib.sha256(events_text.encode()).hexdigest()[:16]  # ties every artifact to this event stream
    n_real = sum(e["origin"] == "real" for e in events)
    counts = {"events": len(events), "real": n_real, "synthetic": len(events) - n_real,
              "real_share": round(n_real / len(events), 3), "households": len(households),
              "registry": len(w.registry), "promises": len(promises), "needles": len(w.needles),
              "decoys": len(w.decoys), "outage_blocks": sum(1 for b in w.blocks.values() if b),
              "by_source": dict(sorted(Counter(e["source"] for e in events).items()))}
    (out / "scenario.json").write_text(json.dumps(contract.scenario_meta({
        "scenario_id": SCENARIO_ID, "revision": revision, "title": "Six Weeks After", "borough": "Queens", "seed": SEED,
        "t0": T0.isoformat(), "ts_unit": "days since storm start", "days": DAYS, "label": LABEL,
        "callback_number": CALLBACK,
        "goal": "Every open promise kept or escalated before its deadline; no opted-in household silent > 3 days.",
        "counts": counts, "outage_blocks": [b for b in w.blocks.values() if b],
    }), indent=1, ensure_ascii=False))
    (out / "events.jsonl").write_text(events_text)
    identity = {h["household_id"]: identity_address(h) for h in w.households}
    for name, obj in [("households_truth", [dict(contract.household(h), identity_address=identity[h["household_id"]])
                                            for h in households]),
                      ("registry", [contract.registry_entry(r) for r in w.registry]), ("personas", personas),
                      ("needles", [dict(contract.needle(n), revision=revision) for n in w.needles]),
                      ("decoys", [dict(d, revision=revision) for d in w.decoys]),
                      ("contact_truth", contact_truth(w, revision)),
                      ("promises", [contract.promise(p) for p in promises]),
                      ("event_truth", w.event_truth_final)]:
        (out / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    (out / "REVIEW.md").write_text(review_md(w, {e["event_id"]: e for e in events}, households))
    return counts


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    target = Path(args[0]) if args else OUT
    if target.resolve() == OUT.resolve() and (OUT / "manifest.json").exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT} is frozen (manifest.json). Regenerate into another directory, e.g. "
                 f"`python data/gen_scenario.py /tmp/s1`, or pass --force only after the PM signs off on a new revision.")
    print(json.dumps(main(target), indent=1))
