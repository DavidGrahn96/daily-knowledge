"""Offline page test: rendered page == data/facts.json for every date, navigation, iPhone layout checks.
Usage: python run.py <repo> <outdir> chromium|webkit"""
import json, sys, time, subprocess, datetime as dt
from pathlib import Path
REPO, OUT, ENGINE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
PORT = 8765 if ENGINE == "chromium" else 8766
LABEL = {"history":"History","science":"Science","geography":"Geography","arts":"Art and literature","music":"Music",
         "philosophy":"Philosophy and religion","economics":"Economics","politics":"Politics and society",
         "language":"Language","technology":"Technology"}
PROBE = (Path(__file__).parent / "probe.js").read_text()
data = json.loads((REPO / "data/facts.json").read_text(encoding="utf-8"))
by = {}
for f in data["facts"]: by.setdefault(f["date"], []).append(f)
dates = sorted(by)
srv = subprocess.Popen([sys.executable, str(Path(__file__).parent / "serve.py"), str(REPO), str(PORT)]); time.sleep(1)
base = f"http://127.0.0.1:{PORT}/"
fails = []
def check(cond, msg):
    if not cond: fails.append(msg)

# ---- engine adapters -------------------------------------------------------
if ENGINE == "chromium":
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start(); br = pw.chromium.launch()
    class Page:
        def __init__(s, w, h, dark=False):
            s.ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=True,
                                   has_touch=True, color_scheme="dark" if dark else "light"); s.p = s.ctx.new_page()
        def open(s, d): s.p.goto(base + f"?d={d}"); s.p.wait_for_function("document.querySelector('#main li.fact')||document.getElementById('statusText').textContent.includes('first fact')")
        def js(s, code): return s.p.evaluate(code)
        def shot(s, path): s.p.screenshot(path=str(path))
        def close(s): s.ctx.close()
else:
    from selenium import webdriver
    from selenium.webdriver.webkitgtk.options import Options
    from selenium.webdriver.webkitgtk.service import Service
    from PIL import Image
    class Page:
        """WebKitGTK cannot shrink its window below ~450px, so the page runs in an iframe of exactly w x h."""
        def __init__(s, w, h, dark=False):
            o = Options(); o.binary_location = "/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/MiniBrowser"; o.add_argument("--automation")
            s.drv = webdriver.WebKitGTK(options=o, service=Service(executable_path="/usr/bin/WebKitWebDriver"))
            s.drv.set_window_size(max(w, 450) + 60, h + 200); s.w, s.h, s.dark = w, h, dark
        def open(s, d):
            s.drv.switch_to.default_content(); s.drv.get(base + f"frame?w={s.w}&h={s.h}&d={d}")
            for _ in range(100):
                try:
                    s.drv.switch_to.default_content(); s.drv.switch_to.frame(0)
                    if s.dark: s.drv.execute_script("document.documentElement.setAttribute('data-theme','dark')")
                    if s.drv.execute_script("return !!document.querySelector('#main li.fact')||document.getElementById('statusText').textContent.includes('first fact')"): break
                except Exception: pass
                time.sleep(0.05)
            assert s.drv.execute_script("return innerWidth") == s.w, "iframe width mismatch"
        def js(s, code): return s.drv.execute_script("return " + code.strip().rstrip(";"))
        def shot(s, path):
            s.drv.switch_to.default_content(); s.drv.save_screenshot(str(path)); s.drv.switch_to.frame(0)
            Image.open(path).crop((0, 0, s.w, s.h)).save(path)
        def close(s): s.drv.quit()

def probe(pg): return pg.js(PROBE)

# ---- A. every date equals facts.json ----------------------------------------
pg = Page(393, 852)
for i, d in enumerate(dates):
    pg.open(d); r = probe(pg)
    exp = [{"label": LABEL[f["category"]], "title": f["title"], "body": f["body"]} for f in by[d]]
    check(r["facts"] == exp, f"{d}: rendered facts differ from facts.json")
    check(r["options"] == list(reversed(dates[:i + 1])) or (i == 0 and r["archiveHidden"]), f"{d}: archive options wrong")
    check(r["recent"] == ["#d" + x for x in reversed(dates[max(0, i - 6):i])], f"{d}: 'days before' wrong {r['recent']}")
    check(r["prevDisabled"] == (i == 0) and r["nextDisabled"], f"{d}: prev/next state wrong")
n_dates = len(dates)
# before start and after the end
pg.open("2026-10-29"); r = probe(pg); check(not r["facts"] and "30 October 2026" in r["status"], "before start not handled")
pg.open("2027-01-05"); r = probe(pg)
check(r["facts"] and r["facts"][0]["title"] == by[dates[-1]][0]["title"] and "no new facts" in r["status"], "after end not handled")

# ---- B. navigation and saving at a shifted date ------------------------------
d0 = "2026-11-05"; pg.open(d0)
pg.js("document.getElementById('prevBtn').click()"); r = probe(pg)
check(r["hash"] == "#d2026-11-04" and r["facts"][0]["title"] == by["2026-11-04"][0]["title"], "Previous failed")
pg.js("(()=>{const s=document.getElementById('archiveSel');s.value='2026-10-31';s.dispatchEvent(new Event('change'));})()"); r = probe(pg)
check(r["hash"] == "#d2026-10-31" and r["facts"][0]["title"] == by["2026-10-31"][0]["title"], "Go to a day failed")
pg.js("document.getElementById('barNext').click()"); r = probe(pg)
check(r["hash"] == "#d2026-11-01", "sticky-bar Next failed")
pg.js("document.getElementById('todayBtn').click()"); r = probe(pg)
check(r["facts"][0]["title"] == by[d0][0]["title"], "Today failed")
pg.js("document.querySelectorAll('#main .star')[1].click()")
saved = json.loads(pg.js("localStorage.getItem('dk:saved')") or "[]")
check([s.get("id") for s in saved] == [f"{d0}|{by[d0][1]['category']}"], f"save id wrong: {saved}")
pg.js("document.getElementById('tabSaved').click()")
check(pg.js("document.querySelectorAll('#main li.fact').length") == 1, "Saved tab does not list the saved fact")
pg.js("localStorage.clear()"); pg.close()

# ---- C. iPhone layout checks and screenshots --------------------------------
for (w, h) in [(375, 667), (393, 852)]:
    for dark in (False, True):
        pg = Page(w, h, dark); pg.open(d0); r = probe(pg)
        tag = f"{ENGINE}_{w}x{h}_{'dark' if dark else 'light'}"
        check(r["firstTitleBottom"] is not None and r["firstTitleBottom"] <= r["innerH"], f"{tag}: first fact title below the fold ({r['firstTitleBottom']} > {r['innerH']})")
        check(r["selectFont"] >= 16, f"{tag}: select font {r['selectFont']}px")
        check(not r["small"], f"{tag}: tap targets under 44px: {r['small']}")
        check(r["barVisible"] and r["barDate"].endswith("5 November 2026"), f"{tag}: sticky bar missing")
        check(r["scrollW"] <= r["clientW"], f"{tag}: horizontal scroll")
        pg.shot(OUT / f"{tag}.png"); pg.close()
pg = Page(320, 640); pg.open(d0); r = probe(pg)
check(r["scrollW"] <= r["clientW"], f"320px: horizontal scroll ({r['scrollW']} > {r['clientW']})"); pg.close()

srv.terminate()
if ENGINE == "chromium": br.close(); pw.stop()
print(f"{ENGINE}: {n_dates} dates, {len(data['facts'])} facts checked; {len(fails)} failure(s)")
for f in fails: print("FAIL", f)
sys.exit(1 if fails else 0)
