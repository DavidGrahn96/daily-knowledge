# Daily Knowledge

Every day: an event that happened on this date, a fun fact, and three things worth knowing, rotating through ten areas: history, science, geography, art and literature, music, philosophy and religion, economics, politics and society, language, and technology.

The site is static and free to host on GitHub Pages. There is no API and no running cost: every fact comes from a pre-written bank in this repo.

## How it works

| Path | Content |
|---|---|
| `bank/<category>.json` | The fact bank, one file per area: `[{"title", "body"}, ...]` |
| `bank/onthisday.json` | One event per calendar day, keyed `"MM-DD"` (366 keys, repeats every year) |
| `bank/namedays.json` | Name days for 10 countries per calendar day; France and Sweden shown under the date, all ten when the date is tapped |
| `bank/words.json` | Word of the day per calendar day in English (C2), French (C1), Swedish (A1–A2), Spanish (B2), Italian (B2) and Portuguese (A1–A2), each checked against Wiktionary (entry exists, part of speech, gender; IPA copied from Wiktionary) |
| `bank/fun.json` | The fun-fact bank: one per day, shown above the area facts |
| `schedule.json` | Start date, facts per day (`per_day`, 3), the rotation order of the areas and the fun-fact bank (`fun`) |
| `scripts/build.py` | Validates the bank and writes the dated schedule |
| `data/facts.json` | Dated record written by `build.py`: a fun fact and three area facts per date (not needed by the page) |
| `topics/<category>.txt` | Planned topic list per area (not used by the site) |
| `index.html` | The page |
| `tests/` | Offline page test (rendered page vs `data/facts.json`, navigation, iPhone layout) |

All facts are numbered *k* = 0, 1, 2, … Fact *k* belongs to area `order[k % 10]` and is entry `floor(k / 10)` of that area's bank file. Day *n* after the start date (2026-10-30) shows facts *k* = 3*n*, 3*n*+1 and 3*n*+2, so the areas rotate: day 0 is history, science, geography; day 1 is art and literature, music, philosophy and religion; and so on. Each day also shows the On this day entry for its calendar date and entry *n* of `bank/fun.json`, the fun fact, above the three. The schedule ends at the first day for which an area or the fun bank has run out; entries beyond that wait. The page applies this rule itself when it loads, shows today's three facts and hides future dates. `build.py` uses the identical rule.

Every entry can carry a `url` to its English Wikipedia article, shown as "Want to know more?". Links were checked against the Wikipedia API (article exists, not a disambiguation page, redirects resolved).

## Adding facts

1. Append new facts to the **end** of the bank files, and keep the areas the **same length** (add the same number of facts to every area in each batch), because the first area to run out ends the schedule. Never reorder or edit published entries, because that would move dates.
2. Run `python scripts/build.py`. It refuses to build if a title repeats, a field is empty or too long, the areas do not reconcile, or a fact dated today or earlier would change (checked per date and area).
3. Keep `bank/fun.json` at least as long as the number of days the areas cover (one fun fact per day).
4. Commit `bank/` and `data/facts.json`. The site updates within a minute or two.

`tests/run.py` checks the rendered page against `data/facts.json` for every date and the iPhone layout rules, in Chromium (Playwright) and WebKit (WebKitGTK via Selenium).

`python scripts/build.py --check` validates and reports how many days of cover remain without writing anything.

Facts are written with the help of an AI and are not individually fact-checked.
