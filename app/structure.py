"""Raw blocks -> a Book: chapters with titles, front/back matter removed, text made speakable."""
import re
from dataclasses import dataclass, field
from .readers import BookError
from .clean import Normaliser, titlecase


@dataclass
class Chapter:
    title: str              # as shown in the player; `spoken` is what is read out
    part: str = ""          # set only where a new part starts
    group: str = ""         # the part this chapter belongs to
    blocks: list = field(default_factory=list)     # [(kind, text)]: p, verse, head, gap, break
    spoken: str = ""
    spoken_part: str = ""


@dataclass
class Book:
    title: str
    author: str
    authors: list
    translator: str
    language: str
    chapters: list
    cover: bytes = b""
    copyrighted: bool = False
    skipped: list = field(default_factory=list)    # [(what, characters)]
    spoken_title: str = ""
    spoken_author: str = ""
    spoken_translator: str = ""
    shrunk: list = field(default_factory=list)     # paragraphs that lost a lot of text in cleaning (should be empty)
    source_chars: int = 0
    kept_chars: int = 0
    notes_removed: int = 0


norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower().replace("’", "").replace("'", "")).strip()
count = lambda s: len(re.sub(r"[\W_]+", "", s))
level = lambda k: int(k[1]) if len(k) == 2 and k[0] == "h" else 0

ORD = r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|last|final"
NUM = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
PART = re.compile(rf"^(part|book|volume|vol|tome)\b( the)? ?({ORD}|{NUM}|[ivxlc]+|\d+|[a-z])?\b|^the ({ORD}) (part|book|volume)\b")
CHAP = re.compile(rf"^(chapter|chap|letter|stave|canto|act|scene|prologue|epilogue|preface|introduction|introductory|foreword|afterword|conclusion|appendix|finale|"
                  rf"postscript|interlude|dedication|prelude|author s (note|preface)|translator s (note|preface)|translators (note|preface)|authors (note|preface))\b|^([ivxlc]+|\d+)( |$)")
SKIP = re.compile(r"^((table of )?contents( of .*)?|(list of |full page )?(illustrations|plates|maps|figures|engravings)( .*)?|list of (the )?(illustrations|plates|maps|figures|engravings|works|books).*|index( of .*| to .*)?|"
                  r"transcriber s? ?notes?.*|transcribers? notes?.*|by the same author.*|(other )?(works|books|novels) by .*|also by .*|advertisements?.*|colophon|copyright.*|bibliography.*|"
                  r"(foot|end)?notes?|errata|corrections|footnotes? .*|the full project gutenberg.*|project gutenberg.*|about the author|cover|title page|half title|acknowledge?ments?|"
                  r"about the publisher|praise for .*|newsletter.*|books? by .*|images?)$")
PG = re.compile(r"project gutenberg|gutenberg\.org|distributed proofread|pgdp\.net|e-?text (was )?(prepared|produced) by|^produced by .{3,160}$|transcribed from the|^scanned by", re.I)


def is_title(n, title, authors):
    t = norm(title); w = n.split()
    if not w: return True
    if n == t: return True
    if len(w) >= 2 and f" {n} " in f" {t} ": return True
    if t.startswith(n) and len(w) >= 1 and len(n) >= 4 and (len(w) >= 2 or len(t.split()) <= 4 or t.split()[0] == n): return True
    names = {x for a in authors for x in norm(a).split() if len(x) > 2}
    if w[0] == "by" and (len(w) == 1 or names & set(w)): return True
    return bool(names) and set(w) <= names | {"by", "the", "author", "of"}


def pick_level(blocks):
    """how deep a heading still starts a chapter"""
    heads = [(i, level(k), t) for i, (k, t) in enumerate(blocks) if level(k)]
    if not heads: return 0
    body = [0] * (len(blocks) + 1)
    for i, (k, t) in enumerate(blocks): body[i + 1] = body[i] + (len(t) if k in ("p", "verse") else 0)
    sizes = {}
    levels = sorted({l for _, l, _ in heads}); L = levels[0]
    for M in levels[1:]:
        tops = [i for i, l, _ in heads if l <= L] + [len(blocks)]
        if tops[0] != 0: tops = [0] + tops
        secs = [(a, b) for a, b in zip(tops, tops[1:]) if body[b] - body[a] > 400 or any(l == M for i, l, _ in heads if a < i < b)]
        have = [s for s in secs if any(l == M for i, l, _ in heads if s[0] < i < s[1])]
        mine = [(i, t) for i, l, t in heads if l == M]
        cut = sorted([i for i, l, _ in heads if l <= M] + [len(blocks)])
        sz = [body[cut[cut.index(i) + 1]] - body[i] for i, _ in mine]
        mean = sum(sz) / max(len(sz), 1)
        chapterish = sum(bool(CHAP.match(norm(t)) or PART.match(norm(t))) for _, t in mine) / len(mine)
        few = sum(1 for a, b in secs if body[b] - body[a] > 400) <= 2
        if secs and (len(have) / len(secs) >= 0.5 or (few and len(mine) >= 2)) and (mean >= 4000 or (chapterish >= 0.5 and mean >= 200) or (few and len(mine) >= 3 and mean >= 300)): L = M
        else: break
    return L


def by_headings(blocks):
    L = pick_level(blocks)
    secs = [dict(heads=[], blocks=[])]
    for k, t in blocks:
        l = level(k)
        if l and l <= L:
            if any(x in ("p", "verse") for x, _ in secs[-1]["blocks"]): secs.append(dict(heads=[], blocks=[]))
            secs[-1]["blocks"] = [b for b in secs[-1]["blocks"] if b[0] != "head"]
            secs[-1]["heads"].append((l, t))
        else: secs[-1]["blocks"].append(("head" if l else k, t))
    return secs


def by_toc(blocks, toc):
    cuts = {}
    for k, lab in toc: cuts.setdefault(k, []).append(lab)
    secs = [dict(heads=[], blocks=[])]
    for i, (k, t) in enumerate(blocks):
        if i in cuts:
            if any(x in ("p", "verse") for x, _ in secs[-1]["blocks"]): secs.append(dict(heads=[], blocks=[]))
            secs[-1]["heads"] += [(1, x) for x in cuts[i]]
        b = ("head" if level(k) else k, t)
        # the printed heading repeats the table-of-contents label
        if not any(x in ("p", "verse") for x, _ in secs[-1]["blocks"]) and any(norm(t) and (norm(t) in norm(h) or norm(h) in norm(t)) and len(t) < len(h) + 40 for _, h in secs[-1]["heads"]): continue
        secs[-1]["blocks"].append(b)
    return secs


def prose(blocks):
    p = [t for k, t in blocks if k == "p"]; total = sum(map(len, p))
    return total > 1500 or (total > 250 and total / max(len(p), 1) > 110)


def build(raw, fallback_title="Untitled"):
    blocks = [b for b in raw.blocks if not (b[0] in ("p", "verse") and PG.search(b[1]) and len(b[1]) < 900)]
    title = raw.title or fallback_title
    if title.isupper(): title = titlecase(title)
    title = re.sub(r"\b([a-z])([a-z]{3,})\b", lambda m: m.group(0) if m.group(0) in ("from", "with", "into", "upon", "over") else m.group(1).upper() + m.group(2), title)   # library style -> title case
    authors = [a for a, _ in raw.authors if norm(a) not in ("", "unknown", "anonymous", "various")]
    author = " and ".join([", ".join(authors[:-1]), authors[-1]] if len(authors) > 1 else authors) or ("various authors" if any(norm(a) == "various" for a, _ in raw.authors) else "an unknown author")

    secs = by_headings(blocks)
    real = sum(1 for s in secs if s["heads"] and prose(s["blocks"]))
    if len({k for k, _ in raw.toc}) >= 2 and real < 0.5 * len({k for k, _ in raw.toc}) and real < 12:
        # block indexes in the TOC refer to the unfiltered list
        alt = by_toc(raw.blocks, raw.toc); alt_real = sum(1 for s in alt if s["heads"] and prose(s["blocks"]))
        if alt_real > real: secs = [dict(heads=s["heads"], blocks=[b for b in s["blocks"] if not (b[0] == "p" and PG.search(b[1]) and len(b[1]) < 900)]) for s in alt]

    skipped, kept, started = [], [], False
    size = lambda s: sum(count(t) for _, t in s["blocks"])
    for s in secs:
        chain = [(l, t, norm(t)) for l, t in s["heads"]]
        last = chain[-1][2] if chain else ""
        if not any(k in ("p", "verse", "head") for k, _ in s["blocks"]):
            # headings without text at the very end, or a part title page that the next section did not absorb
            continue
        if chain and SKIP.match(last):
            skipped.append((chain[-1][1], size(s))); continue
        good = [(l, t, n) for l, t, n in chain if not SKIP.match(n) and not is_title(n, title, authors)]
        named = any(CHAP.match(n) or PART.match(n) for _, _, n in good)
        imprint = not good and not started and real >= 3 and (size(s) < 4000 or re.search(r"all rights reserved|isbn|first published", " ".join(t for _, t in s["blocks"][:60]).lower()))
        if imprint and size(s) < 12000: skipped.append((chain[-1][1] if chain else "text before the first chapter", size(s))); continue
        if not good and chain and not prose(s["blocks"]): skipped.append((chain[-1][1], size(s))); continue
        if not started and not named and not prose(s["blocks"]):
            skipped.append((good[-1][1] if good else "text before the first chapter", size(s))); continue
        if not started and not chain and size(s) < 1500 and len(secs) > 2:
            skipped.append(("text before the first chapter", size(s))); continue
        started = True; kept.append((good, s["blocks"]))
    if not kept:                                   # unusual layout: better one long chapter than none
        every = [b for s in secs for b in s["blocks"]]
        if sum(count(t) for _, t in every) < 200: raise BookError("no chapters with readable text were found")
        kept, skipped = [([], every)], []

    # a printer's imprint as the very last lines
    tail = kept[-1][1]; end = [i for i in range(len(tail)) if tail[i][1]][-4:]
    cut = [i for i in end if tail[i][1].isupper() and re.search(r"\b(PRESS|PRINT(ED|ERS?)|LONDON|NEW YORK|EDINBURGH|STREET|LANE|PUBLISHERS?)\b", tail[i][1])]
    if cut and cut == end[-len(cut):] and sum(len(tail[i][1]) for i in cut) < 300:
        skipped.append(("printer's imprint", sum(count(tail[i][1]) for i in cut))); del tail[cut[0]:]

    # cut printer's lines after "The End"
    tail = kept[-1][1]
    for i in range(len(tail) - 1, max(-1, len(tail) - 60), -1):
        if tail[i][0] in ("p", "verse", "head") and re.fullmatch(r"(the )?end( of .{0,40})?|finis", norm(tail[i][1])):
            rest = tail[i + 1:]
            if sum(count(t) for _, t in rest) < 800:
                if any(t for _, t in rest): skipped.append(("text after “The End”", sum(count(t) for _, t in rest)))
                del tail[i:]
            break

    texts = [t for _, bl in kept for k, t in bl if t]
    N = Normaliser(texts)
    chapters, group, raw_kept, shrunk = [], "", 0, []
    for good, bl in kept:
        part, names = "", []
        for j, (l, t, n) in enumerate(good):
            deeper = any(x[0] > l for x in good[j + 1:])
            if PART.match(n) and j < len(good) - 1 or (deeper and not CHAP.match(n)): part = f"{part}. {t}" if part else t
            else: names.append(t)
        part, name = N.heading(part), N.heading(". ".join(x.rstrip(" .:;,") if x.rstrip()[-1:] in ".:;," else x for x in names))
        newpart = part if part and part != group else ""
        if part: group = part
        elif any(re.match(r"(epilogue|appendix|conclusion|postscript|afterword)\b", n) for _, _, n in good): group = ""
        out = []
        for k, t in bl:
            if k in ("gap", "break"):
                if out and out[-1][0] not in ("gap", "break"): out.append((k, ""))
                continue
            if k == "p" and re.match(r"^\[?transcriber.?s?.? notes?\b", norm(t)): skipped.append(("transcriber's note", count(t))); continue
            x = N.heading(t) if k == "head" else N(t)
            if k == "head": x = N(x)
            raw_kept += count(t)
            if count(t) > 20 and count(x) < 0.6 * count(t): shrunk.append((t[:80], count(t) - count(x)))
            if x and re.search(r"\w", x): out.append((k, x))
        while out and out[-1][0] in ("gap", "break"): out.pop()
        raw_kept += sum(count(t) for _, t, _ in good)
        if out: chapters.append(Chapter(name, newpart, group, out))
    if not chapters: raise BookError("no chapters with readable text were found")
    if len(chapters) == 1 and not chapters[0].title: chapters[0].title = title
    for i, c in enumerate(chapters):
        if not c.title: c.title = "Opening" if i == 0 else f"Section {i + 1}"
    b = Book(title, author, raw.authors, ", ".join(raw.translators), raw.language, chapters, raw.cover, raw.copyrighted, skipped)
    b.notes_removed = raw.notes_removed
    b.source_chars = sum(count(t) for k, t in raw.blocks)
    b.kept_chars = raw_kept
    b.shrunk = shrunk
    for c in chapters: c.spoken, c.spoken_part = N(c.title), N(c.part)
    b.spoken_title, b.spoken_author, b.spoken_translator = N(b.title), N(b.author), N(b.translator)
    return b


STOP = set("the and of to a in that it is was he for with as his on be at by i this had not but from or have an they which you were her she".split())


def looks_english(book):
    lang = book.language.lower().strip()
    sample = " ".join(t for c in book.chapters[:6] for k, t in c.blocks if k == "p")[:30000].lower()
    w = re.findall(r"[^\W\d_]+", sample)
    share = sum(x in STOP for x in w) / max(len(w), 1)
    if len(w) > 200: return share > 0.22
    return not lang or lang.startswith("en")


def mark_title(c, numbered_parts):
    """chapter name shown in the player"""
    t = c.title.rstrip(".")
    return f"{c.group.rstrip('.')}: {t}" if c.group and numbered_parts else t
