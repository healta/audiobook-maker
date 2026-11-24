"""Developer aid: what the author lookup says. usage: dump_authors.py "Name" ["Name|File, As, 1800-1870"] ..."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from app.author import Authors
A = Authors({}, os.path.join(tempfile.mkdtemp(), "cache.json"), True)
for n in sys.argv[1:]:
    a, _, fa = n.partition("|")
    time.sleep(4); i = A.one(a, fa); print(f"{a:34} {i['gender'] or '-':7} {i.get('label', ''):28} {i.get('born', '')}-{i.get('died', '')} {i.get('id', '')} [{i['source']}]", flush=True)
