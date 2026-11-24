"""Folder handling, with a pretend narration process instead of the voice model."""
import json, logging, os, shutil, sys, tempfile, threading, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import settings, worker

FAKE = '''
import json, os, sys, time
d = sys.argv[2]; st = json.load(open(d + "/job.json")); mode = st["file"].split("-")[0]; n = d + "/tries"; t = int(open(n).read()) + 1 if os.path.exists(n) else 1; open(n, "w").write(str(t))
os.makedirs(d + "/chunks", exist_ok=True); print("working on", st["file"], flush=True)
if mode == "slow":
    open(d + "/chunks/%d" % t, "w").close(); time.sleep(60 if t == 1 else 0)
if mode == "bad": open(d + "/error.txt", "w").write("not English"); sys.exit(3)
if mode == "crash": os._exit(9)
if mode == "disk" and t < 5: sys.exit(4)
if mode == "flaky" and t < 5: open(d + "/chunks/%d" % t, "w").close(); os._exit(9)
os.makedirs(d + "/result", exist_ok=True); open(d + "/result/Book.m4b", "w").write("audio")
json.dump(dict(title="Book", author="Ann Other", cover=""), open(d + "/plan.json", "w")); st["stage"] = "done"; json.dump(st, open(d + "/job.json", "w"))
'''


class Worker(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL); self.t = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.t, True); self.addCleanup(logging.disable, logging.NOTSET)
        for k in ("INPUT", "OUTPUT", "PROGRESS", "CONFIG"): setattr(settings, k, os.path.join(self.t, k.lower()))
        settings.ensure(); os.makedirs(os.path.join(self.t, "fake", "app")); open(os.path.join(self.t, "fake", "app", "__init__.py"), "w").close()
        with open(os.path.join(self.t, "fake", "app", "__main__.py"), "w") as f: f.write(FAKE)
        self.old = worker.__file__; worker.__file__ = os.path.join(self.t, "fake", "app", "worker.py"); self.addCleanup(setattr, worker, "__file__", self.old)
        worker.stopping = False; self.sleep = worker.time.sleep; worker.HEARTBEAT = os.path.join(self.t, "beat")

    def put(self, name, text="book", sub=""):
        d = os.path.join(settings.INPUT, sub); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w") as f: f.write(text)

    def take(self):
        w = worker.Watcher(); w.ready(0); p = w.ready(0)
        return worker.claim(p) if p else None

    def go(self, folder, limit=12):
        real = time.sleep; worker.time.sleep = lambda s: real(min(s, 0.05))
        try:
            for i in range(limit):
                if worker.run(folder, lambda f: None): return i + 1
        finally: worker.time.sleep = real
        return 0

    def files(self, d): return sorted(os.path.relpath(os.path.join(a, f), d).replace(os.sep, "/") for a, _, fs in os.walk(d) for f in fs)

    def test_success_and_same_book_again(self):
        for _ in range(2):
            self.put("ok-book.epub"); self.assertEqual(self.go(self.take()), 1)
        self.assertEqual(self.files(settings.OUTPUT), ["Ann Other - Book (2)/Book.m4b", "Ann Other - Book (2)/original.epub", "Ann Other - Book/Book.m4b", "Ann Other - Book/original.epub"])
        self.assertEqual((os.listdir(settings.INPUT), os.listdir(settings.PROGRESS)), ([], []))

    def test_unusable_book_is_not_retried(self):
        self.put("bad-book.txt"); self.assertEqual(self.go(self.take()), 1)
        self.assertEqual(self.files(settings.OUTPUT), ["_failed/bad-book/bad-book.txt", "_failed/bad-book/log.txt", "_failed/bad-book/why.txt"])
        with open(os.path.join(settings.OUTPUT, "_failed", "bad-book", "why.txt")) as f: self.assertIn("not English", f.read())
        self.assertEqual(os.listdir(settings.PROGRESS), [])

    def test_crashes_without_progress_give_up(self):
        self.put("crash-book.txt"); self.assertEqual(self.go(self.take()), 3); self.assertIn("_failed/crash-book/why.txt", self.files(settings.OUTPUT))

    def test_crashes_with_progress_keep_going(self):
        self.put("flaky-book.txt"); self.assertEqual(self.go(self.take()), 5); self.assertIn("Ann Other - Book/Book.m4b", self.files(settings.OUTPUT))

    def test_server_trouble_waits(self):
        self.put("disk-book.txt"); worker_range = worker.range if hasattr(worker, "range") else range
        worker.range = lambda n: worker_range(1)
        try: self.assertEqual(self.go(self.take()), 5)
        finally: del worker.range
        self.assertIn("Ann Other - Book/Book.m4b", self.files(settings.OUTPUT))

    def test_stop_and_resume(self):
        self.put("slow-book.txt"); f = self.take(); threading.Timer(1.5, worker.stop).start(); t = time.time()
        self.assertFalse(worker.run(f, lambda f: None)); self.assertLess(time.time() - t, 20)
        self.assertEqual(worker.read_json(os.path.join(f, "job.json"))["attempts"], 0); self.assertTrue(os.path.exists(os.path.join(f, "source", "slow-book.txt")))
        worker.stopping = False; self.assertEqual(self.go(f), 1); self.assertIn("Ann Other - Book/Book.m4b", self.files(settings.OUTPUT))

    def test_folders_on_different_datasets(self):
        real = os.rename
        def rename(a, b):
            if os.path.dirname(a) != os.path.dirname(b): raise OSError(18, "Invalid cross-device link")
            real(a, b)
        def refuse(*a, **k): raise PermissionError(1, "Operation not permitted")
        with mock.patch("os.rename", rename), mock.patch("os.chmod", refuse), mock.patch("os.utime", refuse):
            self.put("ok-book.epub"); self.put("bad-book.epub")
            while (f := self.take()): self.go(f)
        self.assertEqual((os.listdir(settings.INPUT), os.listdir(settings.PROGRESS)), ([], []))
        out = self.files(settings.OUTPUT); self.assertIn("Ann Other - Book/Book.m4b", out); self.assertIn("_failed/bad-book/bad-book.epub", out); self.assertFalse([x for x in out if ".incoming" in x])

    def test_half_copied_file_waits(self):
        w = worker.Watcher(); self.put("ok-book.epub", "a"); self.assertIsNone(w.ready(0.3)); time.sleep(0.4); self.put("ok-book.epub", "ab"); self.assertIsNone(w.ready(0.3))
        time.sleep(0.4); self.assertIsNotNone(w.ready(0.3))

    def test_ignored_files(self):
        for n in (".hidden.epub", "~$x.txt", "x.epub.part", "Thumbs.db", "_notes.txt", "y.crdownload"): self.put(n)
        self.put("empty.txt", ""); self.put("in.txt", sub=".trash"); self.assertIsNone(self.take())

    def test_subfolder_is_tidied(self):
        self.put("ok-book.epub", sub="Austen/Novels"); self.go(self.take()); self.assertEqual(os.listdir(settings.INPUT), [])

    def test_damaged_job_is_left_alone(self):
        d = os.path.join(settings.PROGRESS, "x"); os.makedirs(os.path.join(d, "source"))
        with open(os.path.join(d, "job.json"), "w") as f: f.write("{")
        self.assertFalse(worker.run(d, lambda f: None)); self.assertFalse(os.path.exists(os.path.join(d, "job.json")))

    def test_finished_before_restart(self):
        self.put("ok-book.epub"); f = self.take(); st = worker.read_json(os.path.join(f, "job.json")); st["stage"] = "done"; worker.write_json(os.path.join(f, "job.json"), st)
        worker.write_json(os.path.join(f, "plan.json"), dict(title="Book", author="A", cover="")); self.assertTrue(worker.run(f, lambda f: None)); self.assertEqual(os.listdir(settings.PROGRESS), [])

    def test_config_mistakes_fall_back(self):
        with open(os.path.join(settings.CONFIG, "config.yaml"), "w") as f: f.write("speed: fast\nvoices:\n  male: am_michael\nnonsense: 1\nscan_every: '7'\n")
        c = settings.load(); self.assertEqual((c["speed"], c["voices"]["male"], c["scan_every"]), (1.0, ["am_michael"], 7))
        with open(os.path.join(settings.CONFIG, "config.yaml"), "w") as f: f.write("voices: [")
        self.assertEqual(settings.load()["voices"], settings.DEFAULTS["voices"])


class Audio(unittest.TestCase):
    def test_loud_pieces_are_not_clipped(self):
        import numpy as np
        from app.job import Job
        w = 1.3 * np.sin(np.linspace(0, 400, 24000)).astype(np.float32)
        m = Job.measure(Job.pcm16(w)); self.assertEqual(m["clip"], 0); self.assertEqual(Job.faults(20, m, 14, m["rms"]), [])


if __name__ == "__main__": unittest.main()
