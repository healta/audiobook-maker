"""Printed text -> speakable text: quotes, dashes, abbreviations, Roman numerals, capitals, old spellings."""
import re, unicodedata
from collections import Counter, defaultdict

ws = lambda s: " ".join(s.split())

# ---------------------------------------------------------------- Roman numerals and ordinals
ROMAN = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
VAL = dict(I=1, V=5, X=10, L=50, C=100, D=500, M=1000)


def roman_value(s):
    s = s.upper()
    if not s or not ROMAN.match(s): return 0
    t = 0
    for a, b in zip(s, s[1:] + " "): t += -VAL[a] if b != " " and VAL[b] > VAL[a] else VAL[a]
    return t


ONES = "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth".split()
TENS = {20: "twent", 30: "thirt", 40: "fort", 50: "fift"}


def ordinal(n):
    if n < 20: return ONES[n]
    t, o = n - n % 10, n % 10
    if t not in TENS: return str(n)
    return TENS[t] + ("ieth" if not o else "y-" + ONES[o])


# ---------------------------------------------------------------- title case
SMALL = set("a an and as at but by for from in into nor of on or the to upon with".split())


def titlecase(s):
    words = s.split(" "); out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^A-Za-z’']", "", w)
        if roman_value(core) and core.isupper() and core not in ("I", "MIX", "DI", "MI", "DID", "MILD", "CIVIL") and len(core) > 0 and not (i and core in ("A",)): out.append(w); continue
        prev_end = i == 0 or words[i - 1][-1:] in ".:;!?—"
        l = w.lower()
        if not prev_end and i < len(words) - 1 and re.sub(r"[^a-z]", "", l) in SMALL: out.append(l); continue
        out.append("-".join(re.sub(r"[^\W\d_]", lambda m: m.group(0).upper(), p, count=1) for p in l.split("-")))
    return " ".join(out)


# ---------------------------------------------------------------- tables
ABBR_NAME = {   # only before a capitalised word
    "Mr": "Mister", "Mrs": "Missus", "Ms": "Miz", "Dr": "Doctor", "Prof": "Professor", "Rev": "Reverend", "Revd": "Reverend", "Capt": "Captain", "Col": "Colonel",
    "Gen": "General", "Lieut": "Lieutenant", "Lt": "Lieutenant", "Maj": "Major", "Sergt": "Sergeant", "Sgt": "Sergeant", "Adm": "Admiral", "Gov": "Governor", "Sen": "Senator",
    "Hon": "Honourable", "Supt": "Superintendent", "Insp": "Inspector", "Messrs": "Messers", "Mme": "Madame", "Mlle": "Mademoiselle", "MM": "Messieurs", "Mons": "Monsieur",
    "Bp": "Bishop", "Abp": "Archbishop", "Cpl": "Corporal", "Pvt": "Private", "Ste": "Sainte", "Mt": "Mount", "Ft": "Fort",
}
ABBR_ANY = {"Mr": "Mister", "Mrs": "Missus", "Dr": "Doctor", "Messrs": "Messers", "Mme": "Madame", "Mlle": "Mademoiselle"}
ABBR_END = {"Esq": "Esquire", "Jr": "Junior", "Jun": "Junior", "Sr": "Senior", "Co": "Company", "Bros": "Brothers", "Ltd": "Limited", "Inc": "Incorporated"}
MONTHS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "Aug": "August", "Sept": "September", "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
_U = ("chapter|chap\\.|book|part|volume|vol\\.|act|scene|canto|letter|section|sect\\.|article|stave|psalm|stanza|appendix|plate|fig\\.|figure|"
      "number|no\\.|lecture|essay|sonnet|ode|page|verse|table|phase")
UNIT = _U + "|" + "|".join(w[0].upper() + w[1:] for w in _U.split("|")) + "|" + _U.upper()
KINGS = (r"Louis|Henry|Charles|George|Edward|William|James|Richard|Philip|Phillip|Napoleon|Pius|Leo|John|Paul|Frederick|Peter|Alexander|Nicholas|Catherine|Elizabeth|Mary|Ivan|Gustavus|"
         r"Ferdinand|Francis|Benedict|Clement|Gregory|Innocent|Urban|Sixtus|Julius|Boniface|Alfonso|Alphonso|Christian|Robert|David|Malcolm|Otto|Joseph|Leopold|Ptolemy|Rameses|Ramses|"
         r"Thutmose|Amenhotep|Victor|Albert|Boleslas|Casimir|Sigismund|Stephen|Constantine|Adrian|Eugenius|Calixtus|Celestine|Martin|Wilhelm|Friedrich|Heinrich|Karl|Henri|Edgar|Baldwin|Amadeus|Mehmed|Murad|Selim")
OLD = {   # same word, older spelling
    "to-day": "today", "to-morrow": "tomorrow", "to-night": "tonight", "shew": "show", "shews": "shows", "shewed": "showed", "shewn": "shown", "shewing": "showing", "connexion": "connection",
    "connexions": "connections", "chuse": "choose", "chuses": "chooses", "chusing": "choosing", "stopt": "stopped", "dropt": "dropped", "fixt": "fixed", "mixt": "mixed", "wrapt": "wrapped",
    "sopha": "sofa", "surprize": "surprise", "surprized": "surprised", "developement": "development", "cloaths": "clothes", "ancle": "ankle", "ancles": "ankles", "gaoler": "jailer", "gaol": "jail",
    "gulph": "gulf", "waggon": "wagon", "waggons": "wagons", "pedler": "peddler", "segar": "cigar", "segars": "cigars", "vallies": "valleys", "encrease": "increase",
    "encreased": "increased", "controul": "control", "untill": "until", "ecstacy": "ecstasy", "recal": "recall", "good-bye": "goodbye", "good-by": "goodbye", "a-going": "a going",
    "burthen": "burden", "burthens": "burdens", "murther": "murder", "phrenzy": "frenzy", "visiter": "visitor", "visiters": "visitors", "negociate": "negotiate", "opprest": "oppressed", "prest": "pressed",
}
CENSORED = {"d-d": "damned", "d-n": "damn", "d-nd": "damned", "d-l": "devil", "g-d": "God", "h-l": "hell", "b-y": "bloody", "b-h": "bitch", "d-": "damn"}
ACRONYMS = set("US USA UK USSR TV OK AM PM BC AD FBI CIA NATO UN EU DNA HIV SS NKVD OGPU GPU KGB".split())
ELISION = re.compile(r"(?<!\w)[’'](?=(?:tis|twas|twere|twill|twould|twixt|em|till|til|cause|bout|gainst|neath|un|im|ere|ave|ouse|ome|arf|alf|cept|specially|pon|fraid|taint|tain|nough|eard|ead|eart)\b)", re.I)
FRAC = {"½": "a half", "¼": "a quarter", "¾": "three quarters", "⅓": "a third", "⅔": "two thirds", "⅛": "an eighth", "⅜": "three eighths", "⅝": "five eighths", "⅞": "seven eighths", "⅕": "a fifth"}


class Normaliser:
    """learns a few habits of the whole book first (quote style, capitals, French titles)"""

    def __init__(self, texts):
        whole = texts
        dbl = sum(t.count("“") + t.count('"') / 2 for t in whole)
        sgl = sum(len(re.findall(r"(?:^|[\s(—-])[‘'](?=[A-Z])", t)) for t in whole)
        self.single = sgl > 2 * dbl and sgl > 10
        self.forms = defaultdict(Counter)
        for t in whole:
            for w in re.findall(r"[A-Za-z][A-Za-z’']*", t):
                if not (w.isupper() and len(w) > 1): self.forms[w.lower().replace("’", "'")][w.replace("’", "'")] += 1
        self.monsieur = sum(len(re.findall(r"\bM\. (?:de |le |du |la )?[A-Z][a-z]", t)) for t in whole) >= 3
        self.bracketed = sum(t.count("[") for t in whole)

    # ------------------------------------------------ quotes
    def quotes(self, t):
        t = t.replace("„", "“").replace("‟", "“").replace("«", "“").replace("»", "”").replace("``", "“").replace("´", "’").replace("`", "‘").replace("‛", "‘").replace("ʼ", "’").replace("''", "”")
        out = []
        for i, c in enumerate(t):
            p = t[i - 1] if i else " "; n = t[i + 1] if i + 1 < len(t) else " "
            if c == '"': out.append("“" if (p.isspace() or p in "([{—–-‘'“") and not n.isspace() else "”")
            else: out.append(c)
        t = "".join(out)
        t = ELISION.sub("'", t)
        t = re.sub(r"(?<=\w)[’‘'](?=\w)", "'", t)                                   # don't, o'clock
        t = re.sub(r"(?<=\w)'(?=\w)", "'", t)
        if self.single: return self.single_to_double(t)
        return self.nested(t)

    @staticmethod
    def nested(t):
        """drop nested single quotes (they carry no sound) but keep elisions: goin', th' old man, the boys' books"""
        out, open_ = [], 0
        for i, c in enumerate(t):
            p = t[i - 1] if i else " "; n = t[i + 1] if i + 1 < len(t) else " "
            if c == "‘": open_ += 1; continue
            if c == "’":
                if p.isalnum() and n.isalpha(): out.append("'"); continue
                if not p.isalpha(): open_ = max(0, open_ - 1); continue
                later = open_ and re.match(r"[^‘]*?(?:[.,!?…—;:]’|\w’(?=[\s.,;:!?”]))", t[i + 1:])
                elided = p == "s" or t[max(0, i - 2):i] in ("in", "an", "th", " o", " t", " i", "wi", "ha")
                if open_ and not (later and elided): open_ -= 1; continue
                out.append("'"); continue
            if c == "'" and not (p.isalnum() or n.isalnum()): continue
            out.append(c)
        return "".join(out)

    @staticmethod
    def single_to_double(t):
        t = re.sub(r"[“”]", "", t)
        out, open_ = [], False
        for i, c in enumerate(t):
            p = t[i - 1] if i else " "; n = t[i + 1] if i + 1 < len(t) else " "
            if c not in "‘’'": out.append(c); continue
            if p.isalnum() and n.isalpha(): out.append("'"); continue
            if c == "'" and re.match(r"(?:tis|twas|twere|twill|twould|em|till|til|bout|neath)\b", t[i + 1:], re.I): out.append("'"); continue
            opening = c == "‘" or (c == "'" and not p.isalnum() and p not in ".,!?…—;:" and not n.isspace())
            if opening: out.append("“"); open_ = True; continue
            if open_:
                rest = t[i + 1:]; k = re.search(r"[‘]", rest); seg = rest[:k.start()] if k else rest
                later = re.search(r"[.,!?…—–;:][’']|[’'](?=[\s.,!?;:]|$)", seg)
                if p in "sz" and n == " " and re.match(r" [a-z]", rest) and later: out.append("'")
                else: out.append("”"); open_ = False
            else: out.append("'")
        return "".join(out)

    # ------------------------------------------------ capitals
    def capitals(self, t):
        toks = list(re.finditer(r"[A-Z][A-Z’']+(?![a-z])|\b[A-Z]\b", t))
        if not toks: return t
        run, runs = [], []
        for m in re.finditer(r"[A-Za-z][A-Za-z’']*", t):
            if m.group(0).isupper() and (len(m.group(0)) > 1 or m.group(0) in "AIO"): run.append(m)
            else: runs.append(run); run = []
        runs.append(run); repl = {}
        for r in runs:
            big = len(r) >= 2 and sum(len(x.group(0)) for x in r) > 6
            for m in r:
                w = m.group(0); lo = w.lower().replace("’", "'")
                if len(w) == 1:
                    if big and w == "A": repl[m.span()] = "a"
                    continue
                if w in ACRONYMS and not big: continue
                base = lo[:-2] if lo.endswith("'s") else lo
                f = self.forms.get(lo) or self.forms.get(base)
                if f:
                    best = f.most_common(1)[0][0]; best = best if lo == best.lower() else best + "'s"
                elif big or (len(w) >= 4 and re.search(r"[AEIOUY]", w)): best = w[0] + w[1:].lower()
                else: continue
                if m.start() == 0 or re.search(r"[.!?]['”]?\s*[“]?$|^[“]$", t[:m.start()][-4:]): best = best[0].upper() + best[1:]
                repl[m.span()] = best
        if not repl: return t
        out, pos = [], 0
        for (a, b), w in sorted(repl.items()): out += [t[pos:a], w]; pos = b
        return "".join(out) + t[pos:]

    # ------------------------------------------------ numerals
    def numerals(self, t):
        t = re.sub(rf"\b({UNIT})\s+([IVXLC]+)\b(\.?)(?=[\s,;:)”—.]|$)", self._unit, t)
        t = re.sub(rf"\b({KINGS})\s+(the\s+)?([IVX]+L?[IVX]*)\b(?!['’])\.?(?=[\s,;:)”—.!?]|$)", lambda m: self._king(m), t)
        def alone(m):
            w = m.group(0); v = roman_value(w)
            return str(v) if v and w not in ("MIX", "DI", "MI", "MD", "DC", "CD", "LI", "MC", "CC", "MM", "CM", "DID", "CIVIL", "MILD", "MIMIC", "VIVID", "LIVID") else w
        return re.sub(r"\b[IVXLC]{2,}\b(?!['’.]\w)", alone, t)

    @staticmethod
    def _unit(m):
        w, v, rest = m.group(2), roman_value(m.group(2)), m.string[m.end(2):]
        if not v or w in ("C", "D", "L", "M", "DI", "MI", "MIX"): return m.group(0)
        if w == "I" and not (re.match(r"[,;:)]|\.\s*$|\s*$|\.[,;)]", rest) and m.group(1)[0].isupper()): return m.group(0)
        return f"{m.group(1)} {v}" + (m.group(3) if not rest[1:].strip() or re.match(r"\.\s+[A-Z“]", rest) else "")

    @staticmethod
    def _king(m):
        v = roman_value(m.group(3))
        if not v or v > 40: return m.group(0)
        if m.group(3) == "I" and m.group(1) in ("Mary", "Paul", "David", "Joseph", "Robert", "Stephen", "Martin", "Victor", "Albert") and not m.group(2): return m.group(0)   # "Mary, I think"
        if m.group(3) == "I" and not m.group(2) and re.match(r"\s+[a-z]", m.string[m.end():]): return m.group(0)       # "Henry I am ..."
        return f"{m.group(1)} the {ordinal(v).capitalize()}" + ("." if m.group(0).endswith(".") and not m.string[m.end():].strip() else "")

    # ------------------------------------------------ abbreviations
    def abbreviations(self, t):
        t = re.sub(r"\bRt\. Hon\.", "Right Honourable", t)
        t = re.sub(r"\b(" + "|".join(ABBR_NAME) + r")\.(?=\s+[“]?[A-Z])", lambda m: ABBR_NAME[m.group(1)], t)
        t = re.sub(r"\b(Mr|Mrs)(?=\s+[A-Z])", lambda m: ABBR_ANY[m.group(1)], t)
        t = re.sub(r"\b(" + "|".join(ABBR_ANY) + r")\.", lambda m: ABBR_ANY[m.group(1)], t)
        if self.monsieur: t = re.sub(r"\bM\.(?=\s+(?:de |le |du |la |d['’])?[A-Z][a-z])", "Monsieur", t)
        t = re.sub(r"\b([A-Z][a-z]+) St\.(?=\s+[a-z]|[,;])", r"\1 Street", t)
        t = re.sub(r"\bSt\.(?=\s*[A-Z])", "Saint ", t)
        for a, b in ABBR_END.items():
            t = re.sub(rf"\b{a}\.(?=\s*$|[”)]\s*$)", b + ".", t); t = re.sub(rf"(?<=[A-Za-z,&] ){a}\.(?=[\s,;:”)])", b, t)
        t = re.sub(r"\b(" + "|".join(MONTHS) + r")\.(?=\s+\d)", lambda m: MONTHS[m.group(1)], t)
        t = re.sub(r"(?:&c|\betc)\.?(?=\s*$|\s+[A-Z“]|[”)])", "etcetera.", t); t = re.sub(r"&c\.?|\betc\.", "etcetera", t)
        t = re.sub(r"\bi\. ?e\.,?", "that is,", t); t = re.sub(r"\be\. ?g\.,?", "for example,", t); t = re.sub(r"\bviz\.,?", "namely,", t); t = re.sub(r"\bcf\.", "compare", t)
        t = re.sub(r"\bvs?\.(?=\s)", "versus", t) if re.search(r"\bvs\.", t) else t
        t = re.sub(r"\b[Nn]os?\.\s*(?=\d)", "number ", t)
        t = re.sub(r"\bpp\.\s*(?=\d)", "pages ", t); t = re.sub(r"\bp\.\s*(?=\d)", "page ", t); t = re.sub(r"\b[Vv]ol\.\s*(?=\d)", "volume ", t); t = re.sub(r"\b[Cc]hap?\.\s*(?=\d)", "chapter ", t)
        t = re.sub(r"\b([AaPp])\. ?([Mm])\.(?=\s+[a-z]|[,;:])", lambda m: (m.group(1) + m.group(2)).upper(), t); t = re.sub(r"\b([AaPp])\. ?([Mm])\.", lambda m: (m.group(1) + m.group(2)).upper() + ".", t)
        t = re.sub(r"\b(A)\. ?(D)\.|\b(B)\. ?(C)\.", lambda m: "A D" if m.group(1) else "B C", t)
        t = re.sub(r"\bPh\. ?D\.", "PhD", t)
        return t

    def money(self, t):
        t = re.sub(r"£\s?([\d,]+)[ .]*(\d{1,2})s\.?(?:\s*(\d{1,2})d\.?)?", lambda m: f"{m.group(1)} pounds, {m.group(2)} shillings" + (f" and {m.group(3)} pence" if m.group(3) else ""), t)
        t = re.sub(r"\b(\d{1,2})s\.\s*(\d{1,2})d\.", r"\1 shillings and \2 pence", t)
        t = re.sub(r"\b(\d{1,2})d\.(?=\s[a-z]|[,;])", r"\1 pence", t)
        t = re.sub(r"\b([\d,]+)\s?l\.(?=\s[a-z])", r"\1 pounds", t)
        for k, v in FRAC.items(): t = re.sub(rf"(?<=\d)\s*{k}", " and " + v, t).replace(k, v)
        t = re.sub(r"(\d)\s*°(?:\s*([FC])\b)?", lambda m: m.group(1) + " degrees" + ({"F": " Fahrenheit", "C": " Celsius"}.get(m.group(2), "")), t)
        return re.sub(r"(?<=\d)[–—-](?=\d)", " to ", t)

    def dashes(self, t):
        t = re.sub(r"-{2,}", "—", t); t = re.sub(r"\s+[–-]\s+", " — ", t).replace("―", "—").replace("–", "—")
        t = re.sub(r"\b([A-Za-z])—+([a-z]{0,2})(?![A-Za-z])", lambda m: CENSORED.get(f"{m.group(1).lower()}-{m.group(2)}", m.group(0)) if m.group(2) else m.group(0), t)
        t = re.sub(r"\b(1[5-9])(?:—+)(?=[\s,.;:)”]|$)", lambda m: {"15": "fifteen", "16": "sixteen", "17": "seventeen", "18": "eighteen", "19": "nineteen"}[m.group(1)] + " hundred and something", t)
        t = re.sub(r"—+\s?shire\b", "blankshire", t)
        t = re.sub(r"\b([A-Z])—+(?=[\s,.;:)”’]|$)", r"\1", t)                         # Mr. B——
        t = re.sub(r"—{2,}", "—", t)
        return re.sub(r"\s*—\s*", lambda m: " — " if " " in m.group(0) else "—", t)

    def tidy(self, t):
        t = unicodedata.normalize("NFC", t)
        t = re.sub(r"[­​-‏﻿⁠]", "", t).replace(" ", " ").replace(" ", " ").replace(" ", " ")
        for a, b in (("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"), ("ﬄ", "ffl"), ("ſ", "s"), ("æ", "ae"), ("Æ", "Ae"), ("œ", "oe"), ("Œ", "Oe")): t = t.replace(a, b)
        t = re.sub(r"https?://\S+|www\.\S+", "", t)
        t = re.sub(r"_([^_\n]{1,400}?)_(?!\w)", r"\1", t).replace("_", " ")
        t = re.sub(r"(?<![\w=])=([^=]+)=(?![\w=])", r"\1", t)
        t = re.sub(r"\[(\d{1,3}|[a-z*†])\]", "", t)
        t = re.sub(r"[\[\]{}<>|~^*#†‡§¶©®™•⁂\\]", " ", t)
        return t

    def __call__(self, t):
        t = self.tidy(t); t = self.dashes(t); t = self.quotes(t)
        t = re.sub(r"\.(?:\s?\.){2,}", "…", t); t = re.sub(r"…\s*\.", "…", t)
        t = self.numerals(t); t = self.capitals(t); t = self.abbreviations(t); t = self.money(t)
        t = t.replace("&", " and ")
        t = re.sub(r"[A-Za-z]+(?:-[A-Za-z]+)*", self._old, t)
        t = re.sub(r"\b([Ee]very|[Aa]ny|[Ss]ome|[Nn]o) (body|thing)\b(?! of)", lambda m: m.group(1) + m.group(2) if m.group(1).lower() != "no" else m.group(0), t)
        t = re.sub(r"“\s+", "“", t); t = re.sub(r"\s+”", "”", t); t = re.sub(r"\s+([,.;:!?…])", r"\1", t); t = re.sub(r"([!?])\1+", r"\1", t)
        t = re.sub(r",(?:\s*,)+", ",", t); t = re.sub(r"\(\s*\)", "", t)
        return ws(t)

    @staticmethod
    def _old(m):
        w = m.group(0); k = w.lower()
        if k in OLD: return OLD[k][0].upper() + OLD[k][1:] if w[0].isupper() else OLD[k]
        return w

    def heading(self, t):
        if not t: return ""
        t = ws(self.tidy(t)); t = re.sub(r"-{2,}|–", "—", t)
        t = re.sub(r"\s*—\s*", " — ", t)
        letters = re.sub(r"[^A-Za-z]", "", t)
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7: t = titlecase(t)
        t = re.sub(rf"\b({UNIT})\s+([IVXLC]+)\b", lambda m: f"{m.group(1)} {roman_value(m.group(2))}" if roman_value(m.group(2)) else m.group(0), t)
        t = re.sub(rf"^({_U.upper()})\b(?=\s|$)", lambda m: m.group(1).capitalize(), t)
        t = re.sub(r"^([IVXLC]+)(?=[.:—\s-]|$)", lambda m: str(roman_value(m.group(1))) if roman_value(m.group(1)) and (m.group(1) != "I" or re.match(r"I\s*([.:—-]|$)", t)) else m.group(1), t)
        t = re.sub(r"\.(?:\s?\.){2,}", "…", t).replace("’", "'").replace("‘", "'")
        return ws(t).strip(" ,;:")
