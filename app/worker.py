"""Watches the input folder and narrates one book at a time.

A book moves input -> in-progress -> output, so it is always in exactly one place. Each book runs in its own child process:
a crash cannot take the watcher down, and the GPU memory is free again when nothing is being narrated.
"""
import json, logging, os, re, shutil, signal, subprocess, sys, time
from . import __version__, dashboard, settings
from .job import TAG, read_json, safe_name, write_json
from .readers import SUPPORTED

log = logging.getLogger("worker")
IGNORE = re.compile(r"^(\.|~|_)|\.(part|partial|crdownload|download|tmp|temp|filepart|!ut)$|^(thumbs\.db|desktop\.ini)$", re.I)
HEARTBEAT = os.environ.get("HEARTBEAT", "/tmp/heartbeat")
stopping = False
child = None
current = None                               # folder of the book being narrated, for the dashboard


def unique(path):
    if not os.path.exists(path): return path
    base, ext = os.path.splitext(path) if os.path.isfile(path) else (path, "")
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"): n += 1
    return f"{base} ({n}){ext}"


def copy(src, dst):
    """contents only: some shares (such as TrueNAS datasets with the SMB preset) do not allow permissions to be copied"""
    if os.path.isdir(src):
        os.makedirs(dst)
        for n in os.listdir(src): copy(os.path.join(src, n), os.path.join(dst, n))
    else: shutil.copyfile(src, dst)


def move(src, dst):
    """move across file systems without ever showing a half-copied file under its final name"""
    dst = unique(dst); os.makedirs(os.path.dirname(dst), exist_ok=True)
    try: os.rename(src, dst); return dst
    except OSError: pass
    tmp = os.path.join(os.path.dirname(dst), ".incoming-" + os.path.basename(dst)[:80])
    if os.path.isdir(tmp): shutil.rmtree(tmp)
    elif os.path.exists(tmp): os.remove(tmp)
    copy(src, tmp); os.rename(tmp, dst)
    shutil.rmtree(src) if os.path.isdir(src) else os.remove(src)
    return dst


class Watcher:
    def __init__(self): self.seen, self.unreadable = {}, set()

    def candidates(self):
        out = []
        for d, dirs, files in os.walk(settings.INPUT):
            dirs[:] = sorted(x for x in dirs if not IGNORE.search(x))
            for f in files:
                if IGNORE.search(f): continue
                p = os.path.join(d, f)
                try: s = os.stat(p)
                except OSError: continue
                if os.path.islink(p) or not os.path.isfile(p): continue
                out.append((s.st_mtime, p, (s.st_size, s.st_mtime_ns)))
        return sorted(out)

    def ready(self, settle):
        """oldest file that has not changed for a while (so half-copied files are left alone)"""
        now, found, cur = time.time(), None, {}
        for _, p, sig in self.candidates():
            old = self.seen.get(p)
            since = old[1] if old and old[0] == sig else now
            cur[p] = (sig, since)
            if sig[0] > 0 and now - since >= settle and found is None:
                try:
                    with open(p, "rb") as f: f.read(1)
                    found = p; self.unreadable.discard(p)
                except OSError as e:
                    if p not in self.unreadable: log.error("cannot read %s: %s (check the folder's permissions)", p, e); self.unreadable.add(p)
        self.seen = cur
        return found


def claim(path):
    """input file -> job folder in in-progress"""
    name = os.path.basename(path); stem = safe_name(TAG.sub("", os.path.splitext(name)[0]), 60)
    folder = unique(os.path.join(settings.PROGRESS, stem)); os.makedirs(os.path.join(folder, "source"))
    write_json(os.path.join(folder, "job.json"), dict(file=name, stage="claimed", attempts=0, added=time.strftime("%Y-%m-%d %H:%M:%S")))
    try: move(path, os.path.join(folder, "source", name))
    except OSError as e:
        shutil.rmtree(folder, ignore_errors=True); log.error("cannot move %s: %s (check the folder's permissions)", path, e); return None
    d = os.path.dirname(path)                      # tidy up subfolders that are now empty
    while os.path.abspath(d) != os.path.abspath(settings.INPUT):
        try: os.rmdir(d)
        except OSError: break
        d = os.path.dirname(d)
    log.info("picked up %s", name)
    return folder


def finish(folder, st):
    plan = read_json(os.path.join(folder, "plan.json")); res = os.path.join(folder, "result")
    if not os.path.isdir(res): shutil.rmtree(folder, ignore_errors=True); return      # already delivered just before a restart
    if settings.load()["keep_original"]:
        src = os.path.join(folder, "source", st["file"])
        if os.path.exists(src): move(src, os.path.join(res, "original" + os.path.splitext(st["file"])[1].lower()))
    if plan["cover"]: shutil.copyfile(os.path.join(folder, plan["cover"]), os.path.join(res, plan["cover"]))
    dst = move(res, os.path.join(settings.OUTPUT, safe_name(f"{plan['author']} - {plan['title']}", 150)))
    shutil.rmtree(folder, ignore_errors=True); log.info("finished: %s", dst)


def fail(folder, st, why):
    src = os.path.join(folder, "source", st["file"]); d = unique(os.path.join(settings.OUTPUT, "_failed", safe_name(os.path.splitext(st["file"])[0], 80))); os.makedirs(d)
    if os.path.exists(src): move(src, os.path.join(d, st["file"]))
    with open(os.path.join(d, "why.txt"), "w", encoding="utf-8") as f: f.write(why.strip() + "\n\nTo try again, move the book back into the input folder.\n")
    lg = os.path.join(folder, "log.txt")
    if os.path.exists(lg): shutil.copyfile(lg, os.path.join(d, "log.txt"))
    shutil.rmtree(folder, ignore_errors=True); log.error("failed: %s (%s)", st["file"], why.strip().splitlines()[0])


def pieces(folder): return sum(len(fs) for _, _, fs in os.walk(os.path.join(folder, "chunks")))


def run(folder, beat):
    """-> True when the job is over (finished or failed)"""
    global child
    try: st = read_json(os.path.join(folder, "job.json"))
    except (OSError, ValueError):
        p = os.path.join(folder, "job.json"); os.replace(p, p + ".damaged")
        log.error("%s has a damaged job.json; leaving the folder alone", folder); return False
    if st.get("stage") == "done": finish(folder, st); return True
    before = pieces(folder); st["attempts"] = st.get("attempts", 0) + 1; write_json(os.path.join(folder, "job.json"), st)
    err = os.path.join(folder, "error.txt")
    if os.path.exists(err): os.remove(err)
    with open(os.path.join(folder, "log.txt"), "a", encoding="utf-8") as lg:
        child = subprocess.Popen([sys.executable, "-u", "-m", "app", "job", folder], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        os.set_blocking(child.stdout.fileno(), False); rest = b""
        while True:
            rc = child.poll(); data = child.stdout.read() or b""
            rest += data
            while b"\n" in rest:
                line, rest = rest.split(b"\n", 1); s = line.decode("utf-8", "replace"); lg.write(s + "\n"); lg.flush(); print(s, flush=True)
            beat(folder)
            if rc is not None and not data: break
            time.sleep(0.5)
    child = None
    st = read_json(os.path.join(folder, "job.json"))
    if stopping:
        st["attempts"] -= 1; write_json(os.path.join(folder, "job.json"), st); return False       # being stopped is not the book's fault
    if rc == 0 and st.get("stage") == "done": finish(folder, st); return True
    why = open(err, encoding="utf-8").read() if os.path.exists(err) else f"the narration process ended unexpectedly (code {rc})" + (", probably out of memory" if rc in (-9, 137) else "")
    if rc == 3: fail(folder, st, why); return True
    if rc == 4:                                     # full disk, missing permission: keep the book and wait
        st["attempts"] -= 1; write_json(os.path.join(folder, "job.json"), st)
        for _ in range(60):
            if stopping: break
            time.sleep(1); beat(folder)
        return False
    if pieces(folder) > before: st["attempts"] = 1; write_json(os.path.join(folder, "job.json"), st)          # it got further, so keep going
    if st["attempts"] >= settings.load()["max_attempts"]: fail(folder, st, why); return True
    log.warning("will try again (%d of %d): %s", st["attempts"] + 1, settings.load()["max_attempts"], why.strip().splitlines()[0]); time.sleep(5)
    return False


def overview(folder=None, queue=0):
    """in-progress/status.txt, readable from the share"""
    try:
        if folder:
            try: s = read_json(os.path.join(folder, "status.json"))
            except (OSError, ValueError): s = dict(book=os.path.basename(folder), step="starting", percent=0)
            eta = s.get("eta_seconds"); t = f"{s['book']}\n{s['step']}: {s.get('percent', 0)}%" + (f", about {int(eta // 3600)} h {int(eta % 3600 // 60)} min left" if eta else "")
        else: t = "Waiting for books."
        t += f"\nBooks waiting: {queue}\nUpdated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        p = os.path.join(settings.PROGRESS, "status.txt")
        with open(p + ".tmp", "w", encoding="utf-8") as f: f.write(t)
        os.replace(p + ".tmp", p)
    except OSError: pass


def stop(*_):
    global stopping
    stopping = True
    if child is not None:
        try: child.terminate()
        except OSError: pass


def watch():
    global current
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop); os.umask(0o002)
    try: settings.ensure()
    except OSError as e:
        log.error("cannot create the folders under %s: %s", settings.DATA, e)
        log.error("give the user this container runs as (%s) write access to that folder, then restart", f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "?"); return 1
    for d in (settings.INPUT, settings.OUTPUT, settings.PROGRESS):
        if not os.access(d, os.W_OK): log.error("cannot write to %s; check its permissions", d); return 1
    c = settings.load(); v = c["voices"]
    log.info("audiobook-maker %s is watching %s (male voices: %s; female voices: %s)", __version__, settings.INPUT, ", ".join(v["male"]) or "none", ", ".join(v["female"]) or "none")
    w = Watcher(); last = [0.0]
    if dashboard.start(w.candidates, lambda: current): log.info("dashboard is on port %s of the container", os.environ.get("DASHBOARD_PORT") or 8080)

    def beat(folder=None):
        if time.time() - last[0] < 5: return
        last[0] = time.time()
        with open(HEARTBEAT, "w") as f: f.write(str(time.time()))
        overview(folder, len([1 for _, p, _ in w.candidates()]))

    while not stopping:
        c = settings.load()
        jobs = sorted((os.path.join(settings.PROGRESS, d) for d in os.listdir(settings.PROGRESS) if os.path.exists(os.path.join(settings.PROGRESS, d, "job.json"))), key=lambda d: os.path.getmtime(os.path.join(d, "job.json")))
        folder = next((j for j in jobs if os.path.exists(os.path.join(j, "source")) ), None)
        try:
            if folder is None:
                p = w.ready(c["settle_seconds"])
                folder = claim(p) if p else None
            if folder is not None:
                current = folder; last[0] = 0; beat(folder); run(folder, beat); current = None; last[0] = 0; continue
        except Exception: log.exception("unexpected problem; carrying on")
        current = None
        beat()
        for _ in range(max(1, int(c["scan_every"]))):
            if stopping: break
            time.sleep(1); beat()
    log.info("stopped; unfinished work continues at the next start"); return 0
