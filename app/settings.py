"""Folders and settings. The config file is created with comments on first start; anything left out falls back to the defaults."""
import logging, os, yaml

log = logging.getLogger("settings")
DATA = os.environ.get("DATA_DIR", "/data")
INPUT = os.environ.get("INPUT_DIR") or os.path.join(DATA, "input")
OUTPUT = os.environ.get("OUTPUT_DIR") or os.path.join(DATA, "output")
PROGRESS = os.environ.get("PROGRESS_DIR") or os.path.join(DATA, "in-progress")
CONFIG = os.environ.get("CONFIG_DIR") or os.path.join(DATA, "config")

DEFAULTS = dict(
    voices=dict(male=["am_michael", "am_puck", "bm_fable"], female=["af_heart", "af_kore", "af_bella"]),
    speed=1.0, device="auto", lookup_author=True, slavic_names="auto",
    intro="{title}. By {author}.", intro_translator="Translated by {translator}.", outro="The end.",
    bitrate="64k", loudness=-20, scan_every=15, settle_seconds=20, keep_original=True, max_attempts=3)

TEMPLATE = """\
# Settings for the audiobook maker. Changes apply to the next book (no restart needed).

# One voice from the matching list is picked at random for each book.
# If the author is unknown, or a book has both male and female authors, all voices take part.
voices:
  male: [am_michael, am_puck, bm_fable]
  female: [af_heart, af_kore, af_bella]

speed: 1.0            # 0.8 slower ... 1.2 faster
device: auto          # auto = GPU if it works, otherwise CPU. Or force: cuda / cpu
lookup_author: true   # ask Wikidata whether the author is male or female (sends only the author's name)
slavic_names: auto    # Russian-style reading of names; auto switches it on when a book has many

intro: "{title}. By {author}."
intro_translator: "Translated by {translator}."   # added only when the book names a translator
outro: "The end."     # "" for none

bitrate: 64k          # AAC, mono
loudness: -20         # LUFS
scan_every: 15        # seconds between looks at the input folder
settle_seconds: 20    # a file must stay unchanged this long before it is picked up
keep_original: true   # put the original book next to the finished audiobook
"""
AUTHORS_TEMPLATE = """\
# Your own say on authors, if the lookup gets one wrong or does not know. Example:
# George Sand: female
"""
LEXICON_TEMPLATE = """\
# Your own pronunciations. Either respell the word...
# Siobhan: Shivawn
# ...or give Kokoro phonemes between slashes:
# Cthulhu: /kəθˈulu/
"""


def ensure():
    for d in (INPUT, OUTPUT, PROGRESS, CONFIG): os.makedirs(d, exist_ok=True)
    for name, text in (("config.yaml", TEMPLATE), ("authors.yaml", AUTHORS_TEMPLATE), ("lexicon.yaml", LEXICON_TEMPLATE)):
        p = os.path.join(CONFIG, name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f: f.write(text)


def read_yaml(name):
    p = os.path.join(CONFIG, name)
    try:
        with open(p, encoding="utf-8-sig") as f: d = yaml.safe_load(f)
        if d is None: return {}
        if isinstance(d, dict): return d
        log.error("%s must be a list of 'name: value' lines; ignoring it", name)
    except FileNotFoundError: pass
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as e: log.error("%s could not be read, ignoring it: %s", name, str(e).replace("\n", " "))
    return {}


def available_voices():
    from .speech import MODELS
    try: return sorted(f[:-3] for f in os.listdir(os.path.join(MODELS, "voices")) if f.endswith(".pt"))
    except OSError: return []


_seen = [None, None]


def load():
    """settings, re-read when the file changes (so a mistake in it is reported once, not every few seconds)"""
    p = os.path.join(CONFIG, "config.yaml")
    try: s = os.stat(p); sig = (p, s.st_mtime_ns, s.st_size, os.environ.get("DEVICE"))
    except OSError: sig = (p, 0, 0, os.environ.get("DEVICE"))
    if _seen[0] != sig: _seen[:] = [sig, _load()]
    return {**_seen[1], "voices": {k: list(v) for k, v in _seen[1]["voices"].items()}}


def _load():
    user = read_yaml("config.yaml"); c = {**DEFAULTS}
    for k, v in user.items():
        if k not in DEFAULTS: log.warning("config.yaml: unknown setting '%s' ignored", k); continue
        if v is None: continue
        if k == "voices":
            if isinstance(v, dict): c["voices"] = {g: [str(x) for x in (v.get(g) or [])] if isinstance(v.get(g) or [], list) else [str(v[g])] for g in ("male", "female")}
            continue
        want = type(DEFAULTS[k])
        try: c[k] = v if k == "slavic_names" or isinstance(v, want) else float(v) if want is float else int(v) if want is int else str(v) if want is str else v
        except (TypeError, ValueError): log.error("config.yaml: '%s: %s' is not valid, using %s", k, v, DEFAULTS[k])
    if os.environ.get("DEVICE"): c["device"] = os.environ["DEVICE"]
    c["speed"] = min(2.0, max(0.5, float(c["speed"])))
    have = set(available_voices())
    for g in ("male", "female"):
        bad = [v for v in c["voices"][g] if have and v not in have]
        if bad: log.error("config.yaml: no such voice: %s (see 'python -m app voices')", ", ".join(bad))
        c["voices"][g] = [v for v in c["voices"][g] if v not in bad]
    if not c["voices"]["male"] and not c["voices"]["female"]: c["voices"] = {k: list(v) for k, v in DEFAULTS["voices"].items()}
    return c
