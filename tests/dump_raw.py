"""Developer aid: show what the readers see in each book. usage: dump_raw.py <book>..."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from app.readers import read_book

for f in sys.argv[1:]:
    r = read_book(f)
    print("=====", os.path.basename(f), "|", r.title, "|", r.authors, r.translators, r.language, "cover", len(r.cover), "blocks", len(r.blocks), "toc", len(r.toc), "notes", r.notes_removed)
    print("   heads", [(k, t[:34]) for k, t in r.blocks if k[0] == "h"][:16])
    print("   first", [(k, t[:60]) for k, t in r.blocks[:6]])
    print("   last ", [(k, t[:60]) for k, t in r.blocks[-3:]])
