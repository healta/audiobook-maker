"""Developer aid: the most common word-level changes made when printed text becomes spoken text."""
import os, sys, re, difflib
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from app.readers import read_book
from app.clean import Normaliser
tok = lambda s: re.findall(r"[\w'’]+|[^\w\s]", s)
for f in sys.argv[2:]:
    r = read_book(f); T = [t for k, t in r.blocks if t and k in ("p", "verse")]; N = Normaliser(T); ch = Counter(); ex = {}
    for t in T:
        a, b = tok(t), tok(N(t))
        for op, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if len(a) < 1500 else []:
            if op != "equal":
                d = (" ".join(a[i:j]), " ".join(b[k:l]))
                if d[0].replace("’", "'") == d[1]: continue
                ch[d] += 1; ex.setdefault(d, " ".join(a[max(0, i-4):j+4]))
    print("=====", os.path.basename(f), "single quotes:", N.single, "monsieur:", N.monsieur)
    for (x, y), n in ch.most_common(int(sys.argv[1])): print(f"  {n:4} {x!r} -> {y!r}   | {ex[(x, y)][:80]}")
    odd = Counter(c for t in T for c in N(t) if ord(c) > 127 and c not in "“”—…" and not c.isalpha())
    print("  odd characters left:", dict(odd))
