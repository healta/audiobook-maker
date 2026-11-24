"""Book files -> a flat stream of raw blocks plus metadata. Understands EPUB, HTML, zipped HTML and plain text.

A raw block is (kind, text) where kind is "h1".."h6", "p", "verse", "gap" (stanza gap) or "break" (scene break).
"""
import html, os, posixpath, re, urllib.parse, zipfile
from dataclasses import dataclass, field
from lxml import etree
import lxml.html


class BookError(Exception):
    """The book cannot be narrated; the message is shown to the user."""


@dataclass
class Raw:
    title: str = ""
    authors: list = field(default_factory=list)      # [(name, file_as)]
    translators: list = field(default_factory=list)
    language: str = ""
    cover: bytes = b""
    blocks: list = field(default_factory=list)       # [(kind, text)]
    toc: list = field(default_factory=list)          # [(block index, label)] when the file has a table of contents
    copyrighted: bool = False                        # Project Gutenberg marks some of its books as still in copyright
    notes_removed: int = 0


BR = "\x0b"
ws = lambda s: " ".join(s.split())
local = lambda e: etree.QName(e).localname.lower() if isinstance(e.tag, str) else None
MAX_FILE = 60 * 1024 * 1024

BLOCK = set("p div section article main body header footer aside blockquote figure figcaption ul ol li dl dt dd table thead tbody "
            "tfoot tr td th caption pre hr center address hgroup details summary fieldset".split())
DROP_TAGS = set("script style head title nav svg math audio video iframe object embed noscript form button select textarea".split())
DROP_CLASS = re.compile(r"^(pagenum\w*|pageno\w*|page-?num(ber)?|pgnum|x-ebookmaker-pageno|folio|pagebreak|caption\w*|figcaption|fig(center|left|right|ure)?|"
                        r"illus\w*|illo\w*|image|toc|contents|footnotes?|fnote|endnotes?|fnanchor|noteref|transnote\w*|tnote\w*|transcriber\w*|"
                        r"pg-?boilerplate|pgheader|pgfooter|sidenote|covernote|advert\w*|hidden)$", re.I)
DROP_ID = re.compile(r"^(pg-header|pg-footer|project-gutenberg-license|toc|footnotes?|endnotes?)$", re.I)
DROP_TYPE = re.compile(r"\b(doc-)?(pagebreak|noteref|footnotes?|endnotes?|rearnotes?|toc|landmarks|index|cover|page-list|loi|lot)\b")
VERSE = re.compile(r"^(poem|poetry|poetry-container|stanza|verse|linegroup|lg|song|hymn|poems?center)$", re.I)
NOTEHREF = re.compile(r"(foot|end)?note|fn|ftn", re.I)
INITIAL = re.compile(r"[“\"‘']?[A-Z]")


def parse_markup(data):
    """bytes -> lxml root. Strict XML first (EPUB), forgiving HTML otherwise."""
    if len(data) > MAX_FILE: raise BookError("a text file inside the book is unreasonably large")
    enc = "utf-8"
    m = re.search(rb"(?:encoding|charset)\s*=\s*[\"']?([A-Za-z0-9_-]+)", data[:2048])
    if m: enc = m.group(1).decode("ascii", "ignore")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"): enc = "utf-16"
    try: s = data.decode("utf-8-sig" if enc.lower().replace("-", "") == "utf8" else enc)
    except (UnicodeDecodeError, LookupError): s = data.decode("utf-8-sig", "replace")
    s = re.sub(r"^\s*<\?xml[^>]*\?>", "", s)
    s = re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", s, count=1, flags=re.I)
    if re.search(r"<html[^>]+xmlns", s[:4000]):
        x = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)(\w+);", _entity, s)
        try: return etree.fromstring(x.encode("utf-8"), etree.XMLParser(resolve_entities=False, no_network=True, recover=False))
        except etree.XMLSyntaxError: pass
        s = re.sub(r"<(a|span|div|p|i|b|em|td|th|li|script|title)(\s[^<>]*)?/>", r"<\1\2></\1>", s)
    return lxml.html.document_fromstring(s.encode("utf-8"), parser=lxml.html.HTMLParser(encoding="utf-8", no_network=True, remove_comments=True))


def _entity(m):
    u = html.unescape(m.group(0))
    return u if u != m.group(0) else "&amp;" + m.group(1) + ";"


class Flow:
    """walks a document and collects raw blocks"""

    def __init__(self, raw):
        self.raw, self.buf, self.link, self.chars, self.ids = raw, [], 0, 0, {}

    def dropped(self, e, tag):
        if tag in DROP_TAGS: return True
        if any(DROP_CLASS.match(c) for c in (e.get("class") or "").split()):
            # a decorated initial sometimes sits in a figure: keep it
            if re.search(r"fnanchor|noteref", e.get("class")): self.raw.notes_removed += 1
            letter = ws("".join(e.itertext())) or ws(" ".join(i.get("alt") or "" for i in e.iter() if local(i) == "img"))
            return not INITIAL.fullmatch(letter)
        if DROP_ID.match(e.get("id") or ""): return True
        kind = " ".join(v for k, v in e.attrib.items() if k.endswith("}type") or k in ("epub:type", "role"))
        if kind and DROP_TYPE.search(kind) and tag != "body": return True
        if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", e.get("style") or ""): return True
        if tag in ("a", "sup"):
            t = ws("".join(e.itertext()))
            if re.fullmatch(r"[\[(]?(\d{1,3}|[*†‡§¶]{1,3}|[A-Za-z])[\])]?", t):
                if tag == "sup" and not re.fullmatch(r"[a-z]", t): self.raw.notes_removed += 1; return True
                href = e.get("href") or ""
                up = e.getparent()
                if tag == "a" and "#" in href and (NOTEHREF.search(href) or t[0] in "[(*†‡§" or (up is not None and local(up) == "sup")):
                    self.raw.notes_removed += 1; return True
        return False

    def text(self, t, inlink):
        if not t: return
        self.buf.append(t); n = len(ws(t)); self.chars += n
        if inlink: self.link += n

    def flush(self, kind="p", verse=False):
        t = "".join(self.buf); link, chars = self.link, self.chars
        self.buf, self.link, self.chars = [], 0, 0
        lines = [ws(x) for x in t.split(BR)]
        lines = [x for x in lines if x]
        if not lines: return
        out = self.raw.blocks
        if kind.startswith("h"):
            t = lines[0]
            for x in lines[1:]: t += (" " if t[-1] in ".,:;!?—-" else ". ") + x
            out.append((kind, t)); return
        whole = " ".join(lines)
        if len(whole) <= 40 and not re.search(r"\w", whole.replace("_", "")):
            out.append(("break", "")); return
        if chars and link / chars > 0.75 and len(whole) < 160:        # a line that is only a link: table of contents, "back to top"
            return
        mean = sum(map(len, lines)) / len(lines)
        if verse or (len(lines) >= 2 and max(map(len, lines)) < 80 and mean < 60):
            out.extend(("verse", x) for x in lines)
            if len(lines) > 1: out.append(("gap", ""))
        else: out.append(("p", whole))

    def walk(self, e, doc="", verse=False, inlink=False):
        tag = local(e)
        if tag is None: return
        if tag == "img":
            alt = ws(e.get("alt") or "")
            if INITIAL.fullmatch(alt): self.text(alt, inlink)
            return
        if tag == "br": self.buf.append(BR); return
        for k in ("id", "name"):
            if e.get(k): self.ids.setdefault(doc + "#" + e.get(k), len(self.raw.blocks))
        if self.dropped(e, tag):
            for d in e.iter():
                if isinstance(d.tag, str) and d.get("id"): self.ids.setdefault(doc + "#" + d.get("id"), len(self.raw.blocks))
            return
        if tag == "hr": self.flush(verse=verse); return
        if re.fullmatch(r"h[1-6]", tag):
            self.flush(verse=verse)
            self.ids.update({doc + "#" + d.get("id"): len(self.raw.blocks) for d in e.iter() if isinstance(d.tag, str) and d.get("id")})
            self.children(e, doc, False, False); self.flush(tag); return
        if tag in BLOCK:
            isverse = verse or any(VERSE.match(c) for c in (e.get("class") or "").split())
            if tag in ("td", "th") :
                self.children(e, doc, isverse, inlink); self.text(" ", False); return
            self.flush(verse=verse)
            if tag == "pre":
                for x in "".join(e.itertext()).split("\n"): self.text(x, inlink); self.buf.append(BR)
                self.flush(verse=isverse); return
            self.children(e, doc, isverse, inlink)
            self.flush(verse=isverse)
            if isverse and not verse and self.raw.blocks and self.raw.blocks[-1][0] == "verse": self.raw.blocks.append(("gap", ""))
            return
        if tag == "span" and verse and re.match(r"^(i\d+|line|verse)$", e.get("class") or ""):      # poem lines as spans
            self.children(e, doc, verse, inlink); self.buf.append(BR); return
        self.children(e, doc, verse, inlink or (tag == "a" and "#" in (e.get("href") or "")))

    def children(self, e, doc, verse, inlink):
        self.text(e.text, inlink)
        for c in e:
            self.walk(c, doc, verse, inlink); self.text(c.tail, inlink)

    def document(self, root, doc=""):
        self.ids.setdefault(doc, len(self.raw.blocks))
        body = next((x for x in root.iter() if local(x) == "body"), root)
        self.walk(body, doc); self.flush()


# ---------------------------------------------------------------- EPUB
def read_epub(path):
    raw = Raw()
    try: z = zipfile.ZipFile(path)
    except zipfile.BadZipFile: raise BookError("not a valid EPUB (the file is damaged or not a zip archive)")
    names = set(z.namelist())
    if sum(i.file_size for i in z.infolist()) > 1_500_000_000: raise BookError("the EPUB expands to more than 1.5 GB")
    if "META-INF/rights.xml" in names or ("META-INF/encryption.xml" in names and _encrypted_text(z)):
        raise BookError("the EPUB is copy-protected (DRM), so its text cannot be read")
    xml = lambda n: etree.fromstring(re.sub(rb"<!DOCTYPE[^>]*>", b"", z.read(n)), etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
    try: opf = next(e.get("full-path") for e in xml("META-INF/container.xml").iter() if local(e) == "rootfile")
    except (KeyError, StopIteration): raise BookError("not a valid EPUB (no package file)")
    o = xml(opf); base = posixpath.dirname(opf)
    full = lambda href, b=base: posixpath.normpath(posixpath.join(b, urllib.parse.unquote(href.split("#")[0])))
    refines = {}
    for m in o.iter():
        if local(m) == "meta" and m.get("refines"): refines.setdefault(m.get("refines").lstrip("#"), {})[m.get("property")] = (m.text or "").strip()
    for e in o.iter():
        t = local(e)
        if t is None: continue
        v = ws("".join(e.itertext()))
        if t == "title" and not raw.title: raw.title = v
        elif t == "language" and not raw.language: raw.language = v
        elif t == "rights" and re.search(r"copyrighted", v, re.I): raw.copyrighted = True
        elif t in ("creator", "contributor") and v:
            r = refines.get(e.get("id"), {})
            get = lambda n: next((x for k, x in e.attrib.items() if k.split("}")[-1] == n), None)
            role = get("role") or r.get("role") or ("aut" if t == "creator" else ""); fa = get("file-as") or r.get("file-as") or ""
            if role == "aut": raw.authors.append((v, fa))
            elif role == "trl": raw.translators.append(v)
    items = {e.get("id"): e for e in o.iter() if local(e) == "item"}
    spine = [items[e.get("idref")] for e in o.iter() if local(e) == "itemref" and e.get("idref") in items and e.get("linear") != "no"]
    cid = next((e.get("content") for e in o.iter() if local(e) == "meta" and e.get("name") == "cover"), None)
    c = next((e for e in items.values() if "cover-image" in (e.get("properties") or "")), None)
    if c is None: c = items.get(cid)
    if c is not None and full(c.get("href")) in names and (c.get("media-type") or "").endswith(("jpeg", "jpg", "png")): raw.cover = z.read(full(c.get("href")))
    flow = Flow(raw)
    for e in spine:
        n = full(e.get("href"))
        if n not in names or "nav" in (e.get("properties") or "").split() or not re.search(r"html|xml", e.get("media-type") or ""): continue
        flow.document(parse_markup(z.read(n)), n)
    raw.toc = _toc(z, xml, items, full, names, flow)
    if not raw.blocks: raise BookError("no readable text found in the EPUB")
    return raw


def _encrypted_text(z):
    s = z.read("META-INF/encryption.xml").decode("utf-8", "replace")
    return any(re.search(r"\.x?html?($|[?#])", u, re.I) for u in re.findall(r'URI="([^"]+)"', s))


def _toc(z, xml, items, full, names, flow):
    out = []
    nav = next((e for e in items.values() if "nav" in (e.get("properties") or "").split()), None)
    ncx = next((e for e in items.values() if "ncx" in (e.get("media-type") or "")), None)
    try:
        if nav is not None and full(nav.get("href")) in names:
            n = full(nav.get("href")); r = parse_markup(z.read(n))
            t = next((x for x in r.iter() if local(x) == "nav" and any("toc" in v for v in x.attrib.values())), None)
            for a in (t.iter() if t is not None else []):
                if local(a) == "a" and a.get("href"): out.append((a.get("href"), ws("".join(a.itertext())), posixpath.dirname(n)))
        if not out and ncx is not None and full(ncx.get("href")) in names:
            n = full(ncx.get("href"))
            for p in xml(n).iter():
                if local(p) == "navpoint":
                    lab = next((ws("".join(x.itertext())) for x in p if local(x) == "navlabel"), "")
                    src = next((x.get("src") for x in p if local(x) == "content"), None)
                    if src: out.append((src, lab, posixpath.dirname(n)))
    except Exception: return []
    res = []
    for href, label, b in out:
        doc = full(href, b); frag = href.split("#")[1] if "#" in href else None
        k = flow.ids.get(f"{doc}#{frag}") if frag else None
        if k is None: k = flow.ids.get(doc)
        if k is not None: res.append((k, label))
    return sorted(set(res))


# ---------------------------------------------------------------- HTML
def read_html(data):
    raw = Raw(); root = parse_markup(data)
    t = next((x for x in root.iter() if local(x) == "title"), None)
    raw.title = ws("".join(t.itertext())) if t is not None else ""
    h = next((x for x in root.iter() if isinstance(x.tag, str) and x.get("id") == "pg-header"), None)
    _pg_meta(raw, ws(" ".join(h.itertext())) if h is not None else "", flat=True)
    flow = Flow(raw); flow.document(root)
    _trim_pg(raw)
    if not raw.blocks: raise BookError("no readable text found in the HTML file")
    return raw


def _pg_meta(raw, head, flat=False):
    if re.search(r"COPYRIGHTED Project Gutenberg|protected by copyright law", head): raw.copyrighted = True
    end = (r"(?=\s+(?:Author|Title|Translator|Illustrator|Editor|Contributor|Release date|Language|Other information|Credits|Original publication|\*\*\*)\s*:?|$)"
           if flat else r"(?=\n\S|\n\s*\n|$)")
    def f(k):
        m = re.search(rf"(?:^|\s){k}\s*:\s*(.+?){end}", head, re.S | re.I)
        return ws(m.group(1)) if m else ""
    raw.title = f("Title") or re.sub(r"^The Project Gutenberg eBook of (the )?|\s*\|\s*Project Gutenberg$", "", raw.title, flags=re.I)
    raw.title = re.sub(r",\s+by\s+[A-Z].*$", "", raw.title)
    if f("Author"): raw.authors = [(a, "") for a in re.split(r"\s+and\s+|\s*;\s*", f("Author"))]
    if f("Translator"): raw.translators = [f("Translator")]
    raw.language = f("Language") or raw.language


def _trim_pg(raw):
    """cut everything outside the START/END markers when they survive as plain text"""
    b = raw.blocks; s, e = 0, len(b)
    for i, (k, t) in enumerate(b):
        if re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", t, re.I): s = i + 1
        if re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG|^End of (the )?Project Gutenberg", t, re.I): e = i; break
    raw.blocks = b[s:e]


# ---------------------------------------------------------------- plain text
CHAPTERISH = re.compile(r"^\s*(chapter|chap\.|letter|stave|canto|act|scene|section|book|part|volume|vol\.|prologue|epilogue|preface|introduction|foreword|afterword|conclusion|appendix|"
                        r"finale|postscript|interlude|dedication|the (first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last) (book|part|chapter))\b", re.I)


def key(s):
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"[\s.·_]+\d+\s*$", "", s.lower()))


def decode_text(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"): return data.decode("utf-16")
    try: return data.decode("utf-8-sig")
    except UnicodeDecodeError: return data.decode("cp1252", "replace")


def read_text(data):
    raw = Raw(); s = decode_text(data).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    if "\x00" in s[:4000]: raise BookError("this does not look like a text file")
    m = re.search(r"^\s*\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG.*?\*{3}[^\n]*$", s, re.M | re.I | re.S)
    _pg_meta(raw, s[:m.start()] if m else s[:3000])
    if m: s = s[m.end():]
    m = re.search(r"^\s*\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG|^\s*End of (?:the )?Project Gutenberg", s, re.M | re.I)
    if m: s = s[:m.start()]
    s = re.sub(r"\[(?:Illustration|Frontispiece|Picture|Map)\b[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]", "", s, flags=re.I)
    s = re.sub(r"\[Footnote[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]", "", s, flags=re.I)
    s = re.sub(r"\[(?:Pg|Page|p\.)\s*[\divxlc]+\]|\{\d{1,4}\}", "", s, flags=re.I)
    s, raw.notes_removed = re.subn(r"(?<=\S)\s?\[(?:\d{1,3}|[A-Z*])\]", "", s)
    groups, cur, blank, gap = [], [], 9, 9                          # groups: [(blank lines before, [lines])]
    for ln in s.split("\n") + [""]:
        if ln.strip():
            if not cur: gap = blank
            cur.append(ln.rstrip()); blank = 0
        else:
            if cur: groups.append((gap, cur)); cur = []
            blank += 1
    # table of contents: everything from "Contents" until an entry shows up again
    entries, skip = set(), None
    for i, (_, ls) in enumerate(groups[:80]):
        if re.fullmatch(r"\s*(table of )?contents\.?\s*", " ".join(ls), re.I):
            for j in range(i + 1, min(len(groups), i + 400)):
                g = groups[j][1]; k = key(" ".join(g))
                if (entries and k in entries) or (len(" ".join(g)) > 220 and not any(CHAPTERISH.match(x) for x in g)): skip = (i, j); break
                entries.update(key(x) for x in g); entries.add(k)
            break
    if skip: groups[skip[0]:skip[1]] = []
    entries.discard("")
    for gap, ls in groups:
        t = ws(" ".join(ls)); n = len(ls)
        if len(t) <= 60 and not re.search(r"\w", t.replace("_", "")): raw.blocks.append(("break", "")); continue
        letters = re.sub(r"[^A-Za-z]", "", t)
        short = n <= 4 and len(t) < 140 and all(len(x.strip()) < 72 for x in ls)
        lead = [x.strip() for x in ls]
        ishead = short and (
            (gap >= 2 and CHAPTERISH.match(t) and not re.search(r"[,;]$", t) and len(t) < 110)
            or (gap >= 2 and len(letters) > 2 and letters.isupper() and not re.search(r"[,;]$", t))
            or (gap >= 2 and re.fullmatch(r"(?:[IVXLC]+|\d{1,3})\.?", t))
            or (gap >= 1 and len(key(t)) > 3 and key(t) in entries))
        if ishead:
            h = lead[0]
            for x in lead[1:]: h += (" " if h[-1] in ".,:;!?—-" else ". ") + x
            raw.blocks.append(("h2" if re.match(r"\s*(book|part|volume|vol\.)\b", t, re.I) else "h3", h)); continue
        ind = [len(x) - len(x.lstrip()) for x in ls]
        poem = (n >= 2 and min(ind) >= 3 and sum(len(x) for x in lead) / n < 56) or (n >= 3 and sum(len(x) for x in lead[:-1]) / (n - 1) < 44 and max(len(x) for x in ls) < 60)
        if poem: raw.blocks.extend(("verse", x) for x in lead); raw.blocks.append(("gap", ""))
        else: raw.blocks.append(("p", t))
    if not raw.blocks: raise BookError("the text file is empty")
    return raw


# ---------------------------------------------------------------- dispatch
SUPPORTED = (".epub", ".txt", ".html", ".htm", ".xhtml", ".zip")


def read_book(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub": return read_epub(path)
    if ext in (".html", ".htm", ".xhtml"):
        with open(path, "rb") as f: return read_html(f.read())
    if ext == ".txt":
        with open(path, "rb") as f: return read_text(f.read())
    if ext == ".zip":
        try: z = zipfile.ZipFile(path)
        except zipfile.BadZipFile: raise BookError("the zip file is damaged")
        n = [i for i in z.infolist() if not i.is_dir() and i.file_size < MAX_FILE and not i.filename.startswith("__MACOSX")]
        if any(i.filename == "META-INF/container.xml" for i in n): return read_epub(path)
        for exts in ((".html", ".htm", ".xhtml"), (".txt",)):
            c = [i for i in n if i.filename.lower().endswith(exts)]
            if len(c) == 1: return (read_text if exts == (".txt",) else read_html)(z.read(c[0]))
        raise BookError("the zip file must contain exactly one HTML or text file")
    raise BookError(f"{ext or 'this'} files are not supported. Convert the book to EPUB first (Calibre does this for MOBI, AZW3 and PDF)")
