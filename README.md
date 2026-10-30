# Daily Knowledge

One piece of general knowledge every day, rotating through ten areas: history, science, geography, art and literature, music, philosophy and religion, economics, politics and society, language, and technology.

The site is static and free to host on GitHub Pages. There is no API and no running cost: every fact comes from a pre-written bank in this repo.

## How it works

| Path | Content |
|---|---|
| `bank/<category>.json` | The fact bank, one file per area: `[{"title", "body"}, ...]` |
| `schedule.json` | Start date and the order in which areas rotate |
| `scripts/build.py` | Validates the bank and writes the dated schedule |
| `data/facts.json` | Optional dated record written by `build.py` (not needed by the page) |
| `index.html` | The page |

Day *n* after the start date gets area `order[n % 10]` and the next unused fact from that area's bank. The page applies this rule itself when it loads, shows today's fact and hides future dates. `build.py` uses the identical rule.

## Adding facts

1. Append new facts to the **end** of the bank files. Never reorder or edit published entries, because that would move dates.
2. Run `python scripts/build.py`. It refuses to build if a title repeats, a field is empty or too long, or a fact dated today or earlier would change.
3. Commit `bank/` (and `data/facts.json` if you keep the dated record). The site updates within a minute or two.

With `data/facts.json` committed, `build.py` also blocks any change to a fact dated today or earlier.

`python scripts/build.py --check` validates and reports how many days of cover remain without writing anything.

Facts are written with the help of an AI and are not individually fact-checked.
