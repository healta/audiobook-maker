"""The dashboard, with made-up folders."""
import http.client, json, logging, os, shutil, sys, tempfile, time, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import dashboard, settings, worker


class Dashboard(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL); self.addCleanup(logging.disable, logging.NOTSET)
        self.t = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.t, True)
        for k in ("INPUT", "OUTPUT", "PROGRESS", "CONFIG"):
            p = mock.patch.object(settings, k, os.path.join(self.t, k.lower())); p.start(); self.addCleanup(p.stop)
        settings.ensure(); self.current = None

    def put(self, path, text="x"):
        p = os.path.join(self.t, path); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(text if isinstance(text, str) else json.dumps(text))
        return p

    def job(self, name, **status):
        d = os.path.join(self.t, "progress", name); os.makedirs(os.path.join(d, "source"))
        self.put(f"progress/{name}/job.json", dict(file=name + ".epub", title="Emma", author="Jane Austen", voice="af_kore"))
        if status: self.put(f"progress/{name}/status.json", status)
        return d

    def state(self): return dashboard.state(worker.Watcher().candidates, lambda: self.current)

    def test_empty(self):
        s = self.state(); self.assertEqual((s["current"], s["queue"], s["done"], s["failed"], s["done_total"]), (None, [], [], [], 0))

    def test_in_progress(self):
        self.current = self.job("emma", step="narrating (af_kore, GPU: GTX 1050 Ti, 4.0 GB, 20.0x real time)", percent=41.5, done=415, total=1000, eta_seconds=600, speed=20.0, device="GPU: GTX 1050 Ti, 4.0 GB")
        c = self.state()["current"]
        self.assertEqual((c["title"], c["author"], c["voice"], c["step"], c["percent"], c["device"], c["speed"]), ("Emma", "Jane Austen", "af_kore", "narrating", 41.5, "GPU", 20.0)); self.assertAlmostEqual(c["left"], 600, delta=5)
        os.utime(os.path.join(self.current, "status.json"), (time.time() - 100,) * 2); self.assertAlmostEqual(self.state()["current"]["left"], 500, delta=5)
        os.utime(os.path.join(self.current, "status.json"), (time.time() - 9999,) * 2); self.assertEqual(self.state()["current"]["left"], 0)

    def test_just_started_or_half_written(self):
        self.current = self.job("emma"); c = self.state()["current"]; self.assertEqual((c["step"], c["left"]), ("starting", None))
        self.put("progress/emma/status.json", "{"); self.put("progress/emma/job.json", ""); self.assertEqual(self.state()["current"]["title"], "emma")

    def test_queue_is_in_reading_order(self):
        for i, n in enumerate(("input/second.txt", "input/Austen/first.epub", "input/.hidden.txt", "input/third.txt.part")): os.utime(self.put(n), (1000 - (i == 1) * 500,) * 2)
        self.current = self.job("now", step="x"); self.job("stopped", step="x")
        self.assertEqual([(q["name"], q["resumes"]) for q in self.state()["queue"]], [("stopped.epub", True), ("Austen/first.epub", False), ("second.txt", False)])

    def test_finished_and_failed(self):
        self.put("output/Jane Austen - Emma/Emma.m4b"); self.put("output/Jane Austen - Emma/report.txt", "Emma\nby Jane Austen, translated by Nobody\n\nLength     15:03:10, 55 chapters, 400 MB\nVoice      af_kore (picked at random)\nAuthor     x\n")
        os.utime(self.put("output/Old Book/Old.m4b"), (1000, 1000)); self.put("output/not a book/notes.txt"); self.put("output/sample.mp3")
        self.put("output/_failed/scan/why.txt", ".pdf files are not supported\n\nTo try again, move it back.\n")
        s = self.state(); self.assertEqual([(b["title"], b["author"], b["length"], b["voice"]) for b in s["done"]], [("Emma", "Jane Austen", "15:03:10", "af_kore"), ("Old Book", "", "", "")])
        self.assertEqual([(f["name"], f["why"]) for f in s["failed"]], [("scan", ".pdf files are not supported")])

    def test_over_http(self):
        self.put("output/X/X.m4b"); self.put("output/X/report.txt", "<script>alert(1)</script>\nby A & B\n")
        s = dashboard.start(worker.Watcher().candidates, lambda: None, port=0); self.addCleanup(s.server_close); self.addCleanup(s.shutdown)
        def get(path, method="GET"):
            c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=5); c.request(method, path); r = c.getresponse(); b = r.read(); c.close(); return r, b
        r, b = get("/"); self.assertEqual(r.status, 200); self.assertIn(b"Audiobooks", b); self.assertIn("default-src 'none'", r.headers["Content-Security-Policy"])
        r, b = get("/status.json?x=1"); self.assertEqual(json.loads(b)["done"][0]["title"], "<script>alert(1)</script>"); self.assertEqual(r.headers["Content-Type"], "application/json")
        for p in ("/../config/config.yaml", "/config/config.yaml", "/app/dashboard.py", "/%2e%2e/", "/status.json/x"): self.assertEqual(get(p)[0].status, 404)
        self.assertEqual(get("/", "HEAD")[1], b""); self.assertEqual(get("/", "POST")[0].status, 501)
        with mock.patch.object(dashboard, "finished", side_effect=RuntimeError): time.sleep(2.1); self.assertEqual(get("/status.json")[0].status, 500)
        time.sleep(0.1); self.assertEqual(get("/status.json")[0].status, 200)

    def test_page_never_builds_html_from_text(self):
        with open(os.path.join(dashboard.HERE, "dashboard.html"), encoding="utf-8") as f: page = f.read()
        for bad in ("innerHTML", "outerHTML", "insertAdjacent", "document.write", "eval(", "http://", "https://"): self.assertNotIn(bad, page)

    def test_port_taken_or_switched_off(self):
        s = dashboard.start(list, lambda: None, port=0); self.addCleanup(s.server_close); self.addCleanup(s.shutdown)
        self.assertIsNone(dashboard.start(list, lambda: None, port=s.server_address[1]))
        for v in ("0", "abc", "99999"):
            with mock.patch.dict(os.environ, DASHBOARD_PORT=v): self.assertIsNone(dashboard.start(list, lambda: None))


if __name__ == "__main__": unittest.main()
