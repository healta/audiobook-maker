"""Developer aid: put a book through every stage on this PC with the ONNX voice. usage: local_job.py <data dir> <book> [voice list]"""
import os, shutil, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [HERE, os.path.join(HERE, "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import logging; logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
from app import settings, worker
from app.job import Job
from onnx_synth import OnnxSynth

settings.ensure()
shutil.copy(sys.argv[2], os.path.join(settings.INPUT, os.path.basename(sys.argv[2])))
w = worker.Watcher(); assert w.ready(0.0) is not None or w.ready(0.0), "file not noticed"
f = worker.claim(w.ready(0.0)); Job(f).run(OnnxSynth)
worker.finish(f, worker.read_json(os.path.join(f, "job.json")))
for d, _, fs in os.walk(settings.OUTPUT):
    for x in fs: print(os.path.relpath(os.path.join(d, x), settings.OUTPUT), os.path.getsize(os.path.join(d, x)))
print("left in input:", os.listdir(settings.INPUT), "left in progress:", os.listdir(settings.PROGRESS))
