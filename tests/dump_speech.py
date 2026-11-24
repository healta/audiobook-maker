"""Developer aid: phonemes, chunk sizes and unknown words for a book. usage: dump_speech.py <config.json> a|b <book>..."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from app import lexicon
from app.readers import read_book
from app.structure import build
from app.speech import Phonemizer, Planner
vocab = json.load(open(sys.argv[1], encoding="utf-8"))["vocab"]; brit = sys.argv[2] == "b"
for name in ("FIXES", "CLASSICS", "RUSSIAN"):
    bad = {w: [c for c in p if c not in vocab] for w, p in getattr(lexicon, name).items() if any(c not in vocab for c in p)}
    print(name, len(getattr(lexicon, name)), "bad symbols:", bad)
for f in sys.argv[3:]:
    b = build(read_book(f)); T = [t for c in b.chapters for _, t in c.blocks]
    P = Phonemizer(brit, T, vocab); L = Planner(P)
    ch = [x for c in b.chapters[:8] for x in L.chunks(c.blocks)]
    n = [len(x["ph"]) for x in ch]
    print("==", os.path.basename(f), "slavic", P.lex.slavic, "| chunks in 8 chapters", len(ch), "median", sorted(n)[len(n)//2], "max", max(n), "over 400:", sum(x > 400 for x in n))
    print("   unknown:", ", ".join(f"{w}({k})" for w, k in P.lex.unknown(40)))
    for w in ("Petrovitch", "Razumihin", "Svidrigaïlov", "Ivanovna", "Semyonovna", "Zametov", "Antoine", "Brontë", "fancied", "copied", "denied", "Svidrigaïlov's"):
        if w in P.lex.words: print("    ", w, P(w))
