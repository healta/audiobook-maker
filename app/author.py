"""Find out whether an author is recorded as male or female, so a fitting voice can be picked.

Order: the user's own list (config/authors.yaml) -> remembered answers -> an unmistakable title in the name ("Mrs. Gaskell")
-> Wikidata. Nothing is guessed from first names: if none of these knows, the answer is "" and any voice may be used.
Only the author's name is sent to Wikidata, and only when lookup_author is on.
"""
import json, logging, math, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request

log = logging.getLogger("author")
API = "https://www.wikidata.org/w/api.php?"
AGENT = {"User-Agent": "audiobook-maker/1.0", "Accept": "application/json"}
MALE, FEMALE = {"Q6581097", "Q2449503"}, {"Q6581072", "Q1052281"}
WRITER = {"Q36180", "Q6625963", "Q49757", "Q214917", "Q11774202", "Q4853732", "Q15949613", "Q4964182", "Q201788", "Q333634", "Q1930187", "Q11499147", "Q18844224", "Q482980", "Q15980158",
          "Q1607826", "Q14467526", "Q864380", "Q487596", "Q18939491", "Q13570226", "Q37226", "Q901", "Q1234713", "Q250867", "Q6051619", "Q8178443", "Q22073916", "Q12144794"}
fold = lambda s: re.sub(r"[^a-z0-9]+", " ", "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))).strip()


def plain_name(name, file_as=""):
    """"Austen, Jane, 1775-1817" / "Leo Tolstoy, graf" / "L. Frank (Lyman Frank) Baum" -> (name, (birth, death))"""
    y = re.search(r"(\d{4})\s*\??\s*[-–]\s*(\d{4})?", f"{name} {file_as}")
    years = (int(y.group(1)), int(y.group(2)) if y.group(2) else 0) if y else (0, 0)
    n = re.sub(r"\([^)]*\)", " ", name)
    n = re.sub(r",?\s*(\d{4}\??\s*[-–]?\s*(\d{4})?\??|active.*|\d+(st|nd|rd|th) cent.*)$", "", n.strip()).strip(" ,")
    parts = [p.strip() for p in n.split(",") if p.strip()]
    # title fragments after a comma are dropped, "Surname, Forename" is turned round
    if len(parts) > 1:
        n = parts[0] if re.fullmatch(r"(graf|count|baron|sir|lord|esq\.?|jr\.?|m\.?d\.?|ph\.?d\.?|saint|duke.*|earl.*|lady|dame|mrs\.?)", parts[1], re.I) and " " in parts[0] else f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", n).strip(), years


def by_title(name):
    if re.match(r"(mrs|miss|lady|madame|mme|mademoiselle|dame|countess|baroness|duchess|princess|queen|sister|mother|empress|marchioness)\b\.?\s", name, re.I): return "female"
    if re.match(r"(mr|sir|lord|monsieur|king|pope|brother|father|prince|emperor|duke|earl|baron)\b\.?\s", name, re.I): return "male"
    return ""


WAITS = [5, 20, 60, 120]             # a failed lookup would cost the book its fitting voice, so be patient


def fetch(params):
    url = API + urllib.parse.urlencode({**params, "format": "json", "maxlag": 5})
    for wait in WAITS + [None]:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=20) as r: d = json.loads(r.read(4_000_000))
            if "error" not in d: time.sleep(1); return d
            err = OSError(d["error"].get("info", "unknown error")[:200])
            if d["error"].get("code") not in ("maxlag", "ratelimited", "readonly"): raise ValueError(str(err))
        except urllib.error.HTTPError as e:
            err = e
            if e.code not in (429, 500, 502, 503, 504): raise
            after = e.headers.get("Retry-After", "")
            if wait is not None and after.isdigit(): wait = min(300, max(wait, int(after)))
        except (urllib.error.URLError, TimeoutError, OSError) as e: err = e
        if wait is None: raise err
        log.info("Wikidata is busy or unreachable (%s); trying again in %d s", err, wait); time.sleep(wait)


def ids(ent, prop):
    out = []
    for c in ent.get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated": continue
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        out.append(v.get("id") if isinstance(v, dict) and "id" in v else v)
    return out


def year(ent, prop):
    for v in ids(ent, prop):
        if isinstance(v, dict) and (m := re.match(r"([+-]\d+)", v.get("time", ""))): return int(m.group(1))
    return 0


def wikidata(name, years=(0, 0)):
    """-> dict(gender, label, born, died, id) or {}"""
    r = fetch(dict(action="wbsearchentities", search=name, language="en", uselang="en", type="item", limit=10))
    cand = [x["id"] for x in r.get("search", [])]
    if not cand: return {}
    ents = fetch(dict(action="wbgetentities", ids="|".join(cand), props="claims|labels|aliases|sitelinks", languages="en")).get("entities", {})
    best = None
    for q in cand:
        e = ents.get(q, {})
        if "Q5" not in ids(e, "P31"): continue
        names = {fold(e.get("labels", {}).get("en", {}).get("value", ""))} | {fold(a["value"]) for a in e.get("aliases", {}).get("en", [])}
        if fold(name) not in names:
            if not (set(fold(name).split()) <= set(" ".join(names).split()) and fold(name).split()[-1] in " ".join(names).split()): continue
            s = 0
        else: s = 2
        writer = bool(set(ids(e, "P106")) & WRITER)
        gutenberg = bool(ids(e, "P1938"))
        s += 5 * gutenberg + 2 * writer + min(3, math.log10(1 + len(e.get("sitelinks", {}))) * 1.5)
        b, d = year(e, "P569"), year(e, "P570")
        for have, want in ((b, years[0]), (d, years[1])):
            if want and have: s += 4 if abs(have - want) <= 1 else -5
        g = set(ids(e, "P21"))
        gender = "female" if g & FEMALE else "male" if g & MALE else ""
        if (writer or gutenberg) and (best is None or s > best[0]):
            best = (s, dict(gender=gender, label=e.get("labels", {}).get("en", {}).get("value", name), born=b, died=d, id=q))
    return best[1] if best and best[0] >= 3 else {}


class Authors:
    def __init__(self, overrides, cache_path, lookup=True):
        self.over = {fold(str(k)): str(v).lower() for k, v in (overrides or {}).items()}
        self.path, self.lookup = cache_path, lookup
        try:
            with open(cache_path, encoding="utf-8") as f: self.cache = json.load(f)
        except (OSError, ValueError): self.cache = {}

    def one(self, name, file_as=""):
        """-> dict(gender, source, died, ...)"""
        n, years = plain_name(name, file_as); k = fold(n)
        for x in (k, fold(name)):
            if self.over.get(x) in ("male", "female"): return dict(gender=self.over[x], source="your authors.yaml", name=n)
        if k in self.cache: return {**self.cache[k], "source": self.cache[k].get("source", "Wikidata") + " (remembered)", "name": n}
        info = {}
        if self.lookup and k:
            try:
                info = wikidata(n, years)
                if not info and len(n.split()) > 2:            # "Mary Wollstonecraft Shelley" style full names
                    w = n.split(); info = wikidata(f"{w[0]} {w[-1]}", years)
            except Exception as e: log.warning("could not ask Wikidata about %s: %s", n, e); info = None
        if info and info.get("gender"):
            self.cache[k] = {**info, "source": "Wikidata"}; self.save()
            return {**info, "source": "Wikidata", "name": n}
        t = by_title(name)
        if t: return dict(gender=t, source="the title in the name", name=n)
        return {**(info or {}), "gender": "", "source": "lookup failed" if info is None else "not found" if not info else "Wikidata has no gender", "name": n}

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(self.cache, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e: log.warning("could not save %s: %s", self.path, e)

    def book(self, authors):
        """authors of one book -> (gender or "", [info per author])"""
        infos = [self.one(n, fa) for n, fa in authors if fold(n) not in ("", "unknown", "anonymous", "various")]
        g = {i["gender"] for i in infos}
        return (g.pop() if len(g) == 1 else ""), infos
