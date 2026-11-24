"""Build step: download the Kokoro model and the English voices from one fixed revision and check every file.

usage: fetch_models.py <target dir> <models.sha256>
"""
import hashlib, os, sys, time, urllib.request

REV = "f3ff3571791e39611d31c381e3a41a3af07b4987"
BASE = f"https://huggingface.co/hexgrad/Kokoro-82M/resolve/{REV}/"
target, sums = sys.argv[1], sys.argv[2]
want = [line.split() for line in open(sums, encoding="ascii") if line.strip() and not line.startswith("#")]
assert len(want) > 2, "models.sha256 is empty"
for sha, name in want:
    path = os.path.join(target, name); os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(1, 6):
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(BASE + name, headers={"User-Agent": "audiobook-maker-build"})
            with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
                while b := r.read(1 << 20): f.write(b); h.update(b)
            break
        except OSError as e:
            if attempt == 5: raise
            print(f"{name}: {e}; trying again", flush=True); time.sleep(5 * attempt)
    if h.hexdigest() != sha: sys.exit(f"{name}: checksum is {h.hexdigest()}, expected {sha}")
    print("ok", name, flush=True)
