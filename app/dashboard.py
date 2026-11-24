"""A small read-only web page: what is being narrated, what is waiting, what is finished. Standard library only."""
import json, logging, os, re, socketserver, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import __version__, settings

log = logging.getLogger("dashboard")
HERE = os.path.dirname(os.path.abspath(__file__))
SHOW = 300                                  # finished books listed (newest first)
seen = {}                                   # report.txt -> (modified, what it says)


def load(path):
    try:
        with open(path, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError): return {}


def folders(path):
    try:
        with os.scandir(path) as it: return [e.path for e in it if e.is_dir() and not e.name.startswith((".", "_"))]
    except OSError: return []


def job(folder):
    """the book being narrated"""
    st, s = load(os.path.join(folder, "job.json")), load(os.path.join(folder, "status.json"))
    left = s.get("eta_seconds")
    if left is not None:
        try: left = max(0, left - (time.time() - os.path.getmtime(os.path.join(folder, "status.json"))))
        except OSError: pass
    return dict(title=st.get("title") or st.get("file") or os.path.basename(folder), author=st.get("author", ""), voice=st.get("voice", ""), step=str(s.get("step", "starting")).split(" (")[0],
                percent=s.get("percent", 0), done=s.get("done", 0), total=s.get("total", 0), left=left, speed=s.get("speed"), device=str(s.get("device") or "").split(":")[0].split(" ")[0])


def report(folder):
    """title, author, length and voice, as written in a finished book's report.txt"""
    p = os.path.join(folder, "report.txt")
    try: m = os.stat(p).st_mtime_ns
    except OSError: return {}
    if p in seen and seen[p][0] == m: return seen[p][1]
    out = {}
    try:
        with open(p, encoding="utf-8", errors="replace") as f: lines = [f.readline(500).strip() for _ in range(8)]
        out["title"] = lines[0]
        for x in lines[1:]:
            if x.startswith("by ") and "author" not in out: out["author"] = x[3:].split(", translated by ")[0]
            elif r := re.match(r"Length\s+([\d:]+)", x): out["length"] = r.group(1)
            elif r := re.match(r"Voice\s+(\S+)", x): out["voice"] = r.group(1)
    except OSError: return {}
    seen[p] = (m, out)
    return out


def finished():
    out = []
    for d in folders(settings.OUTPUT):
        try:
            with os.scandir(d) as it: when = max((e.stat().st_mtime for e in it if e.name.lower().endswith(".m4b") and not e.name.startswith(".")), default=None)
        except OSError: continue
        if when is not None: out.append((when, d))
    out.sort(reverse=True)
    return len(out), [dict(title=os.path.basename(d), author="", length="", voice="", when=when) | report(d) for when, d in out[:SHOW]]


def failed():
    out = []
    for d in folders(os.path.join(settings.OUTPUT, "_failed")):
        try:
            with open(os.path.join(d, "why.txt"), encoding="utf-8", errors="replace") as f: why = f.readline(500).strip()
            out.append(dict(name=os.path.basename(d), why=why, when=os.path.getmtime(os.path.join(d, "why.txt"))))
        except OSError: continue
    return sorted(out, key=lambda x: -x["when"])[:SHOW]


def state(candidates, current):
    now = current()
    waiting = [dict(name=load(os.path.join(d, "job.json")).get("file") or os.path.basename(d), size=None, resumes=True)
               for d in folders(settings.PROGRESS) if d != now and os.path.exists(os.path.join(d, "job.json")) and os.path.isdir(os.path.join(d, "source"))]
    waiting += [dict(name=os.path.relpath(p, settings.INPUT).replace(os.sep, "/"), size=sig[0], resumes=False) for _, p, sig in candidates()]
    n, done = finished()
    return dict(version=__version__, time=time.time(), current=job(now) if now and os.path.isdir(now) else None, queue=waiting, done=done, done_total=n, failed=failed())


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def server_bind(self):                  # the standard one looks up the host's name, which can hang without a DNS server
        socketserver.TCPServer.server_bind(self); self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request, address): pass


def handler(get_state):
    with open(os.path.join(HERE, "dashboard.html"), "rb") as f: page = f.read()
    lock, cache = threading.Lock(), [0.0, b""]

    def status():
        with lock:                          # however many pages are open, the folders are looked at no more than every two seconds
            if time.monotonic() - cache[0] > 2 or not cache[1]: cache[1] = json.dumps(get_state()).encode(); cache[0] = time.monotonic()
            return cache[1]

    class Handler(BaseHTTPRequestHandler):
        timeout, server_version, sys_version = 15, "audiobook-maker", ""

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path == "/": self.answer(200, "text/html; charset=utf-8", page)
                elif path == "/status.json": self.answer(200, "application/json", status())
                else: self.answer(404, "text/plain", b"not found")
            except (BrokenPipeError, ConnectionError, TimeoutError): pass
            except Exception:
                log.exception("the dashboard could not answer"); self.answer(500, "text/plain", b"error, see the log")

        do_HEAD = do_GET

        def answer(self, code, kind, body):
            self.send_response(code)
            for k, v in (("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                         ("Content-Security-Policy", "default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'")): self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)

        def log_message(self, *a): pass

    return Handler


def start(candidates, current, port=None):
    """runs beside the watcher; a problem here never stops the narration"""
    try:
        if port is None:
            port = int(os.environ.get("DASHBOARD_PORT") or 8080)
            if port == 0: return None
        s = Server(("", port), handler(lambda: state(candidates, current)))
    except (OSError, ValueError, OverflowError) as e:
        log.error("the dashboard could not start: %s", e); return None
    threading.Thread(target=s.serve_forever, name="dashboard", daemon=True).start()
    return s
