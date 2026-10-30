"""Serve the repo; /?d=YYYY-MM-DD injects a fixed-clock Date shim before the page script."""
import http.server, sys, re, functools
from urllib.parse import urlparse, parse_qs
ROOT = sys.argv[1]; PORT = int(sys.argv[2])
SHIM = ('<script>(function(){{const R=Date,F=new R({y},{m},{d},12).getTime();'
        'function D(...a){{return a.length?new R(...a):new R(F);}}D.prototype=R.prototype;'
        'D.now=()=>F;D.UTC=R.UTC;D.parse=R.parse;window.Date=D;}})();</script>')
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/frame":
            w, h, d = q["w"][0], q["h"][0], q["d"][0]
            b = (f'<!DOCTYPE html><html><body style="margin:0"><iframe id="f" src="/?d={d}" '
                 f'style="border:0;display:block;width:{w}px;height:{h}px"></iframe></body></html>').encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(b)); self.end_headers(); self.wfile.write(b); return
        if u.path in ("/", "/index.html"):
            html = open(f"{ROOT}/index.html", encoding="utf-8").read()
            html = re.sub(r'<link[^>]+fonts\.(googleapis|gstatic)[^>]*>', '', html)  # no external fonts offline
            if "d" in q:
                y, m, d = map(int, q["d"][0].split("-"))
                html = html.replace("<head>", "<head>" + SHIM.format(y=y, m=m - 1, d=d), 1)
            b = html.encode(); self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", len(b))
            self.end_headers(); self.wfile.write(b); return
        return super().do_GET()
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=ROOT)).serve_forever()
