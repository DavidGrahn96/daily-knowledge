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


def schedule(bank: dict[str, list[dict]], order: list[str], start: date, per_day: int) -> list[dict]:
    out, n = [], 0
    while True:
        slots = [fact_at(bank, order, per_day * n + j) for j in range(per_day)]
        if None in slots:
            return out  # an area has run out: the schedule ends before this day
        d = (start + timedelta(days=n)).isoformat()
        for cat, idx in slots:
            f = bank[cat][idx]
            out.append({"date": d, "category": cat, "title": f["title"].strip(), "body": f["body"].strip()})
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
        if per_day < 1 or len(set(order)) != len(order):
            raise BuildError("schedule.json: per_day must be >= 1 and areas must be unique")
        bank = load_bank(args.root / "bank", order)
        facts = schedule(bank, order, start, per_day)
        if not facts:
            raise BuildError("Schedule is empty")

        # Reconciliation: exactly per_day facts per date, consecutive dates from the start,
        # and fact number k (in schedule order) equals the bank entry k points to.
        dates = sorted({f["date"] for f in facts})
        if len(facts) != len(dates) * per_day or dates[0] != start.isoformat() or \
           dates[-1] != (start + timedelta(days=len(dates) - 1)).isoformat():
            raise BuildError("Reconciliation failed: dates are not consecutive with per_day facts each")
        for k, f in enumerate(facts):
            cat, idx = order[k % len(order)], k // len(order)
            b = bank[cat][idx]
            if (f["category"], f["title"], f["body"]) != (cat, b["title"].strip(), b["body"].strip()):
                raise BuildError(f"Reconciliation failed at fact {k} ({f['date']} {f['category']})")
        per_cat = {c: sum(1 for f in facts if f["category"] == c) for c in order}
        unused = {c: len(bank[c]) - per_cat[c] for c in order if len(bank[c]) > per_cat[c]}

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
        log.info("%d facts scheduled = %d days, %s to %s (%d days of cover from %s)", len(facts), len(dates),
                 dates[0], dates[-1], (last - args.today).days, args.today)
        if unused:
            log.info("Waiting (not yet scheduled): %s", unused)
        if args.check:
            return 0
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump({"start": start.isoformat(), "per_day": per_day, "order": order, "facts": facts}, fh,
                      ensure_ascii=False, indent=1)
            fh.write("\n")
        log.info("Wrote %s", out_path)
        return 0
    except (BuildError, KeyError, ValueError, OSError) as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
