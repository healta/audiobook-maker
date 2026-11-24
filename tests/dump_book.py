"""Developer aid: show the chapters a book turns into. usage: dump_book.py [-v] <book>..."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from app.readers import read_book, BookError
from app.structure import build, looks_english, mark_title

v = "-v" in sys.argv
for f in [a for a in sys.argv[1:] if a != "-v"]:
    try: r = read_book(f); b = build(r)
    except BookError as e: print("=====", os.path.basename(f), "REJECTED:", e); continue
    parts = len({c.group for c in b.chapters if c.group}) > 1
    print("=====", os.path.basename(f), "|", b.title, "| by", b.author, "| trans.", b.translator, "| english", looks_english(b), "| chapters", len(b.chapters),
          f"| kept {b.kept_chars} of {b.source_chars} = {100*b.kept_chars/b.source_chars:.1f}% | shrunk {len(b.shrunk)} {b.shrunk[:3]}")
    print("   skipped:", b.skipped)
    for i, c in enumerate(b.chapters):
        if v or i < 4 or i >= len(b.chapters) - 2:
            ps = [t for k, t in c.blocks if k == "p"]
            print(f"   {i+1:3} {('['+c.part+'] ') if c.part else ''}{mark_title(c, parts)!r} {sum(len(t) for _, t in c.blocks)} chars: {c.blocks[0][1][:70]!r} ... {c.blocks[-1][1][-40:]!r}")
