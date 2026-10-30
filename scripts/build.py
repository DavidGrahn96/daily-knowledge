"""Build data/facts.json from the fact bank.

Usage (from the repo root):
    python scripts/build.py              # validate, schedule, write
    python scripts/build.py --check      # validate only, write nothing

How the schedule works
  Day n after the start date gets category order[n % 10] and the next unused
  fact in that category's bank file. Appending facts to the END of a bank file
  never moves an existing date. Editing or reordering existing facts would, so
  the build refuses to change any fact dated today or earlier unless you pass
  --allow-past-changes.

Checks
  - every fact has a non-empty title (<= 80 chars) and body (<= 600 chars)
  - no duplicate titles, case-insensitive, across the whole bank
  - published facts (date <= today) are unchanged versus the current facts.json
  - reconciliation: every scheduled fact traces back to exactly one bank entry
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


def schedule(bank: dict[str, list[dict]], order: list[str], start: date) -> list[dict]:
    out, n = [], 0
    while True:
        cat = order[n % len(order)]
        idx = n // len(order)
        if idx >= len(bank[cat]):
            return out  # the first category to run out ends the schedule
        f = bank[cat][idx]
        out.append({"date": (start + timedelta(days=n)).isoformat(), "category": cat,
                    "title": f["title"].strip(), "body": f["body"].strip()})
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
        order, start = cfg["order"], date.fromisoformat(cfg["start"])
        bank = load_bank(args.root / "bank", order)
        facts = schedule(bank, order, start)
        if not facts:
            raise BuildError("Schedule is empty")

        # Reconciliation: scheduled count per category equals bank entries consumed.
        per_cat = {c: sum(1 for f in facts if f["category"] == c) for c in order}
        for c in order:
            if [(f["title"], f["body"]) for f in facts if f["category"] == c] != \
               [(b["title"].strip(), b["body"].strip()) for b in bank[c][:per_cat[c]]]:
                raise BuildError(f"Reconciliation failed for {c}")
        unused = {c: len(bank[c]) - per_cat[c] for c in order if len(bank[c]) > per_cat[c]}

        out_path = args.root / "data" / "facts.json"
        if out_path.exists():
            old = {f["date"]: f for f in read_json(out_path)["facts"]}
            new = {f["date"]: f for f in facts}
            changed = [d for d, f in old.items() if d <= args.today.isoformat() and new.get(d) != f]
            if changed and not args.allow_past_changes:
                raise BuildError(f"Would change {len(changed)} published day(s), first {changed[0]}. "
                                 "Append new facts to the end of bank files instead.")

        last = date.fromisoformat(facts[-1]["date"])
        log.info("%d facts scheduled, %s to %s (%d days of cover from %s)", len(facts), facts[0]["date"],
                 facts[-1]["date"], (last - args.today).days, args.today)
        if unused:
            log.info("Bank entries waiting for other categories to catch up: %s", unused)
        if args.check:
            return 0
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump({"start": start.isoformat(), "order": order, "facts": facts}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        log.info("Wrote %s", out_path)
        return 0
    except (BuildError, KeyError, ValueError, OSError) as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
