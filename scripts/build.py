"""Build data/facts.json from the fact bank.

Usage (from the repo root):
    python scripts/build.py              # validate, schedule, write
    python scripts/build.py --check      # validate only, write nothing

How the schedule works (identical rule in index.html)
  All facts are numbered k = 0, 1, 2, ... Fact k is area order[k % len(order)]
  and entry k // len(order) of that area's bank file. Day n after the start
  date shows facts k = P*n ... P*n + P-1, where P is "per_day" in
  schedule.json (3). The schedule ends at the first day for which any of its
  facts is missing, i.e. when an area runs out. Entries beyond that point are
  reported as "waiting". Appending facts to the END of bank files never moves
  an existing date; keep the areas the same length. Editing or reordering
  existing facts would change dates, so the build refuses to change any fact
  dated today or earlier (compared per date and category) unless you pass
  --allow-past-changes.

  On this day: if schedule.json names an "onthisday" bank, each date also shows
  the entry for its calendar day ("MM-DD", 366 keys), first. It never runs out.
  Every entry may carry a "url" (an English Wikipedia article) and On this day
  entries carry the "year" of the event.

  Name days: if schedule.json names a "namedays" file, it is validated here
  (366 day keys, a list per country per day) and shown by the page by
  calendar day; it is not part of data/facts.json.

  Words of the day: if schedule.json names a "words" file, it is validated here
  (366 day keys, one word per language, no repeats within a language, a
  Wiktionary url each) and shown by the page by calendar day.

  Fun fact: if schedule.json names a "fun" bank (bank/fun.json), day n also
  shows entry n of that file, above the area facts. The schedule then also
  ends when the fun bank runs out. In data/facts.json it is the first entry of
  each date, with category "fun".

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


def schedule(bank: dict[str, list[dict]], order: list[str], start: date, per_day: int,
             fun: str | None = None, otd: dict[str, dict] | None = None) -> list[dict]:
    """Dated facts. With a fun bank, each day starts with fun fact n, and the schedule also ends
    when the fun bank runs out."""
    out, n = [], 0
    while True:
        slots = [fact_at(bank, order, per_day * n + j) for j in range(per_day)]
        if None in slots or (fun and n >= len(bank[fun])):
            return out  # an area (or the fun bank) has run out: the schedule ends before this day
        d = (start + timedelta(days=n)).isoformat()
        if otd:
            out.append(entry(d, "onthisday", otd[d[5:]]))
        for cat, idx in ([(fun, n)] if fun else []) + slots:
            out.append(entry(d, cat, bank[cat][idx]))
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
        order, start, per_day = cfg["order"], date.fromisoformat(cfg["start"]), int(cfg["per_day"])
        fun = cfg.get("fun")  # optional: name of the fun-fact bank file, one per day, shown first
        if per_day < 1 or len(set(order)) != len(order) or fun in order:
            raise BuildError("schedule.json: per_day must be >= 1 and areas (and the fun bank) must be unique")
        bank = load_bank(args.root / "bank", order + ([fun] if fun else []))
        seen = {f["title"].strip().casefold() for c in bank for f in bank[c]}
        otd = load_onthisday(args.root / "bank" / f"{cfg['onthisday']}.json", seen) if cfg.get("onthisday") else None
        if cfg.get("words"):
            check_words(args.root / "bank" / f"{cfg['words']}.json")
        if cfg.get("namedays"):
            check_namedays(args.root / "bank" / f"{cfg['namedays']}.json")
        all_facts = schedule(bank, order, start, per_day, fun, otd)
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
        for k, f in enumerate(facts):
            cat, idx = order[k % len(order)], k // len(order)
            b = bank[cat][idx]
            if (f["category"], f["title"], f["body"], f.get("url")) != (cat, b["title"].strip(), b["body"].strip(), b.get("url") or None):
                raise BuildError(f"Reconciliation failed at fact {k} ({f['date']} {f['category']})")
        per_cat = {c: sum(1 for f in facts if f["category"] == c) for c in order}
        unused = {c: len(bank[c]) - per_cat[c] for c in order if len(bank[c]) > per_cat[c]}
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
            json.dump({"start": start.isoformat(), "per_day": per_day, "order": order, "fun": fun,
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
