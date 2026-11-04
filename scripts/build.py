"""Build data/facts.json from the fact bank.

Usage (from the repo root):
    python scripts/build.py              # validate, schedule, write
    python scripts/build.py --check      # validate only, write nothing

How the schedule works (this script is the only scheduler; index.html shows data/facts.json)
  All area facts are numbered k = 0, 1, 2, ... Day n after the start date shows
  k = P*n ... P*n + P-1 (P = "per_day", 3). Fact k goes to slot
  order[k % 10] of the phase in force that day ("phases" in schedule.json). A
  slot draws the next unused entry from its source bank(s); a slot with two
  sources (e.g. "arts": ["arts", "music"]) alternates between them. Bank
  pointers carry over between phases, so a new phase never moves an earlier
  date. The schedule ends before the first day a slot cannot be filled.
  Appending facts to the END of bank files never moves an existing date. The
  build refuses to change any fact dated today or earlier (compared per date
  and category) unless you pass --allow-past-changes.

  On this day: if schedule.json names an "onthisday" bank, each date also shows
  the entry for its calendar day ("MM-DD", 366 keys), first. It never runs out.
  Every entry may carry a "url" (an English Wikipedia article) and On this day
  entries carry the "year" of the event.

  Words of the day / name days: validated here (366 day keys each) and shown
  by the page by calendar day; not part of data/facts.json.

  Fun fact: if schedule.json names a "fun" bank (bank/fun.json), day n also
  shows entry n of that file, above the area facts. The schedule then also
  ends when the fun bank runs out. In data/facts.json it is the second entry
  of each date, with category "fun".

Checks
  - every fact has a non-empty title (<= 80 chars) and body (<= 600 chars)
  - no duplicate titles, case-insensitive, across the whole bank
  - published facts (date <= today) are unchanged versus the current facts.json
  - reconciliation: exactly P facts per date, and every scheduled fact equals
    the bank entry its number k points to
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

MAX_TITLE, MAX_BODY = 80, 600
log = logging.getLogger("build")


class BuildError(Exception):
    pass


def read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_bank(bank_dir: Path, order: list[str]) -> dict[str, list[dict]]:
    bank, seen = {}, {}
    for cat in order:
        path = bank_dir / f"{cat}.json"
        if not path.exists():
            raise BuildError(f"Missing bank file: {path}")
        items = read_json(path)
        for i, f in enumerate(items, 1):
            title, body = str(f.get("title", "")).strip(), str(f.get("body", "")).strip()
            where = f"{path.name} item {i}"
            if not title or not body:
                raise BuildError(f"{where}: empty title or body")
            if len(title) > MAX_TITLE or len(body) > MAX_BODY:
                raise BuildError(f"{where}: title or body too long ({len(title)}/{len(body)} chars)")
            if f.get("url") and not str(f["url"]).startswith("https://en.wikipedia.org/wiki/"):
                raise BuildError(f"{where}: url must be an English Wikipedia article")
            key = title.casefold()
            if key in seen:
                raise BuildError(f"{where}: duplicate title {title!r} (also {seen[key]})")
            seen[key] = where
        bank[cat] = items
    return bank


def fact_at(bank: dict[str, list[dict]], order: list[str], k: int) -> tuple[str, int] | None:
    """Area and bank index of fact number k, or None if that area has run out."""
    cat, idx = order[k % len(order)], k // len(order)
    return (cat, idx) if idx < len(bank[cat]) else None


def entry(d: str, cat: str, f: dict) -> dict:
    e = {"date": d, "category": cat, "title": f["title"].strip(), "body": f["body"].strip()}
    if f.get("year") is not None:
        e["year"] = f["year"]
    if f.get("url"):
        e["url"] = f["url"]
    return e


def load_onthisday(path: Path, seen_titles: set[str]) -> dict[str, dict]:
    """bank/onthisday.json: {"MM-DD": {"year", "title", "body", "url"}} for all 366 calendar days."""
    otd = read_json(path)
    want = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d") for i in range(366)}
    if set(otd) != want:
        raise BuildError(f"{path.name}: needs exactly the 366 keys MM-DD; missing {sorted(want - set(otd))[:5]}, "
                         f"extra {sorted(set(otd) - want)[:5]}")
    for k, f in otd.items():
        title, body = str(f.get("title", "")).strip(), str(f.get("body", "")).strip()
        if not title or not body or not isinstance(f.get("year"), int):
            raise BuildError(f"{path.name} {k}: needs title, body and an integer year")
        if len(title) > MAX_TITLE or len(body) > MAX_BODY:
            raise BuildError(f"{path.name} {k}: title or body too long")
        if title.casefold() in seen_titles:
            raise BuildError(f"{path.name} {k}: duplicate title {title!r}")
        seen_titles.add(title.casefold())
        if f.get("url") and not str(f["url"]).startswith("https://en.wikipedia.org/wiki/"):
            raise BuildError(f"{path.name} {k}: url must be an English Wikipedia article")
    return otd


def check_namedays(path: Path) -> None:
    """bank/namedays.json: {"countries": {code: {name, source}}, "days": {"MM-DD": {code: [names]}}}."""
    nd = read_json(path)
    codes = set(nd["countries"])
    want = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d") for i in range(366)}
    if set(nd["days"]) != want:
        raise BuildError(f"{path.name}: needs exactly the 366 day keys MM-DD")
    for k, day in nd["days"].items():
        if set(day) != codes or not all(isinstance(v, list) and all(isinstance(n, str) and n.strip() for n in v)
                                        for v in day.values()):
            raise BuildError(f"{path.name} {k}: every country needs a list of names (may be empty)")
    for c in codes:
        filled = sum(1 for day in nd["days"].values() if day[c])
        if filled < 340:
            raise BuildError(f"{path.name}: {c} has names on only {filled} days")


def check_words(path: Path) -> None:
    """bank/words.json: {"languages": {code: {name, level}}, "days": {"MM-DD": {code: {word, pos, meaning, example, url, ...}}}}."""
    wd = read_json(path)
    codes = set(wd["languages"])
    want = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d") for i in range(366)}
    if set(wd["days"]) != want:
        raise BuildError(f"{path.name}: needs exactly the 366 day keys MM-DD")
    seen = {c: {} for c in codes}
    for k, day in wd["days"].items():
        if set(day) != codes:
            raise BuildError(f"{path.name} {k}: every language needs a word")
        for c, w in day.items():
            if not all(str(w.get(f, "")).strip() for f in ("word", "pos", "meaning", "example", "url")):
                raise BuildError(f"{path.name} {k} {c}: word, pos, meaning, example and url are required")
            if c != "en" and not str(w.get("example_en", "")).strip():
                raise BuildError(f"{path.name} {k} {c}: example_en is required")
            if not w["url"].startswith("https://en.wiktionary.org/wiki/"):
                raise BuildError(f"{path.name} {k} {c}: url must be an English Wiktionary page")
            key = w["word"].casefold()
            if key in seen[c]:
                raise BuildError(f"{path.name} {k} {c}: {w['word']!r} repeats {seen[c][key]}")
            seen[c][key] = k


def load_phases(cfg: dict) -> list[dict]:
    """schedule.json "phases": [{"from": date, "order": [10 slot names], "slots": {slot: [source banks]}}].
    Older files with a single top-level "order" are one phase from the start date."""
    phases = cfg.get("phases") or [{"from": cfg["start"], "order": cfg["order"]}]
    out = []
    for i, ph in enumerate(phases):
        order = ph["order"]
        if len(set(order)) != len(order):
            raise BuildError(f"schedule.json phase {i}: slot names must be unique")
        out.append({"from": date.fromisoformat(ph["from"]), "order": order,
                    "slots": {s: ph.get("slots", {}).get(s, [s]) for s in order}})
    if out[0]["from"] != date.fromisoformat(cfg["start"]) or \
       any(a["from"] >= b["from"] for a, b in zip(out, out[1:])):
        raise BuildError("schedule.json: phases must start at 'start' and be in date order")
    if len({len(p["order"]) for p in out}) != 1:
        raise BuildError("schedule.json: every phase needs the same number of slots")
    return out


def schedule(bank: dict[str, list[dict]], phases: list[dict], start: date, per_day: int,
             fun: str | None = None, otd: dict[str, dict] | None = None) -> list[dict]:
    """Dated facts.

    All area facts are numbered k = 0, 1, 2, ...; day n shows k = per_day*n ... per_day*n + per_day-1.
    Fact k goes to slot order[k % len(order)] of the phase in force on that day. A slot draws the next
    unused entry from its source bank(s); a slot with several sources takes them in turn (a, b, a, b, ...),
    skipping a source that has run out. Bank pointers carry over between phases, so a change of phase
    never moves an earlier date. The schedule ends before the first day that cannot be filled (or when
    the fun bank runs out). Each entry's "category" is its slot; "source" names the bank if different."""
    ptr = {c: 0 for c in bank}
    turn = {}                      # (phase index, slot) -> next source position
    out, n = [], 0
    while True:
        d_date = start + timedelta(days=n)
        pi = max(i for i, p in enumerate(phases) if p["from"] <= d_date)
        ph = phases[pi]
        L = len(ph["order"])
        picks, saved_ptr, saved_turn = [], dict(ptr), dict(turn)
        for j in range(per_day):
            k = per_day * n + j
            slot = ph["order"][k % L]
            srcs = ph["slots"][slot]
            t = turn.get((pi, slot), 0)
            pick = None
            for step in range(len(srcs)):
                src = srcs[(t + step) % len(srcs)]
                if ptr[src] < len(bank[src]):
                    pick = (slot, src, ptr[src]); ptr[src] += 1; turn[(pi, slot)] = t + step + 1
                    break
            if pick is None:
                break
            picks.append(pick)
        if len(picks) < per_day or (fun and n >= len(bank[fun])):
            ptr.update(saved_ptr); turn.clear(); turn.update(saved_turn)
            return out  # a slot (or the fun bank) has run out: the schedule ends before this day
        d = d_date.isoformat()
        if otd:
            out.append(entry(d, "onthisday", otd[d[5:]]))
        if fun:
            out.append(entry(d, fun, bank[fun][n]))
        for slot, src, idx in picks:
            e = entry(d, slot, bank[src][idx])
            if src != slot:
                e["source"] = src
            out.append(e)
        n += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="override today (YYYY-MM-DD)")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--allow-past-changes", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        cfg = read_json(args.root / "schedule.json")
        start, per_day = date.fromisoformat(cfg["start"]), int(cfg["per_day"])
        phases = load_phases(cfg)
        fun = cfg.get("fun")  # optional: name of the fun-fact bank file, one per day, shown first
        sources = list(dict.fromkeys(src for p in phases for s in p["order"] for src in p["slots"][s]))
        if per_day < 1 or fun in sources:
            raise BuildError("schedule.json: per_day must be >= 1 and the fun bank cannot be an area")
        bank = load_bank(args.root / "bank", sources + ([fun] if fun else []))
        seen = {f["title"].strip().casefold() for c in bank for f in bank[c]}
        otd = load_onthisday(args.root / "bank" / f"{cfg['onthisday']}.json", seen) if cfg.get("onthisday") else None
        if cfg.get("words"):
            check_words(args.root / "bank" / f"{cfg['words']}.json")
        if cfg.get("namedays"):
            check_namedays(args.root / "bank" / f"{cfg['namedays']}.json")
        all_facts = schedule(bank, phases, start, per_day, fun, otd)
        if not all_facts:
            raise BuildError("Schedule is empty")

        # Reconciliation: exactly per_day area facts (plus one fun fact) per date, consecutive dates
        # from the start, fact number k equals the bank entry k points to, and day n's fun fact is fun[n].
        facts = [f for f in all_facts if f["category"] not in (fun, "onthisday")]
        if otd and [f["date"] for f in all_facts if f["category"] == "onthisday"] != sorted({f["date"] for f in all_facts}):
            raise BuildError("Reconciliation failed: not exactly one On this day entry per date")
        dates = sorted({f["date"] for f in all_facts})
        if len(facts) != len(dates) * per_day or dates[0] != start.isoformat() or \
           dates[-1] != (start + timedelta(days=len(dates) - 1)).isoformat():
            raise BuildError("Reconciliation failed: dates are not consecutive with per_day facts each")
        if fun:
            funs = [f for f in all_facts if f["category"] == fun]
            if [f["date"] for f in funs] != dates or [(f["title"], f["body"]) for f in funs] != \
               [(b["title"].strip(), b["body"].strip()) for b in bank[fun][:len(dates)]]:
                raise BuildError("Reconciliation failed: fun facts do not match bank/%s.json day by day" % fun)
        # Each fact sits in the slot its phase gives fact number k, and every source bank is used in
        # order from the start, each entry exactly once.
        used = {c: [] for c in sources}
        for k, f in enumerate(facts):
            ph = phases[max(i for i, p in enumerate(phases) if p["from"] <= date.fromisoformat(f["date"]))]
            src = f.get("source", f["category"])
            if f["category"] != ph["order"][k % len(ph["order"])] or src not in ph["slots"][f["category"]]:
                raise BuildError(f"Reconciliation failed at fact {k} ({f['date']} {f['category']}): wrong slot")
            used[src].append((f["title"], f["body"], f.get("url")))
        for c in sources:
            if used[c] != [(b["title"].strip(), b["body"].strip(), b.get("url") or None) for b in bank[c][:len(used[c])]]:
                raise BuildError(f"Reconciliation failed for bank {c}: entries not used in order")
        unused = {c: len(bank[c]) - len(used[c]) for c in sources if len(bank[c]) > len(used[c])}
        if fun and len(bank[fun]) > len(dates):
            unused[fun] = len(bank[fun]) - len(dates)
        facts = all_facts

        out_path = args.root / "data" / "facts.json"
        if out_path.exists():
            old = {(f["date"], f["category"]): f for f in read_json(out_path)["facts"]}
            new = {(f["date"], f["category"]): f for f in facts}
            changed = sorted(k for k, f in old.items() if k[0] <= args.today.isoformat() and new.get(k) != f)
            if changed and not args.allow_past_changes:
                raise BuildError(f"Would change {len(changed)} published fact(s), first {changed[0][0]} "
                                 f"{changed[0][1]}. Append new facts to the end of bank files instead.")
            if changed:
                log.warning("--allow-past-changes: %d published fact(s) changed, first %s %s",
                            len(changed), *changed[0])

        last = date.fromisoformat(dates[-1])
        log.info("%d facts scheduled (incl. %d fun facts) = %d days, %s to %s (%d days of cover from %s)",
                 len(facts), len(dates) if fun else 0, len(dates),
                 dates[0], dates[-1], (last - args.today).days, args.today)
        if unused:
            log.info("Waiting (not yet scheduled): %s", unused)
        if args.check:
            return 0
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump({"start": start.isoformat(), "per_day": per_day, "phases": cfg.get("phases"), "fun": fun,
                       "onthisday": cfg.get("onthisday"), "facts": facts}, fh,
                      ensure_ascii=False, indent=1)
            fh.write("\n")
        log.info("Wrote %s", out_path)
        return 0
    except (BuildError, KeyError, ValueError, OSError) as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
