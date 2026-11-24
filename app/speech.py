"""Text -> phonemes -> chunks -> audio (Kokoro-82M on the GPU, or on the CPU when there is no usable GPU)."""
import json, logging, os, re, time
import numpy as np
from .lexicon import Lexicon

SR = 24000
TARGET, SOFT, HARD = 190, 260, 400          # phonemes per chunk; Kokoro reads 100-200 best and starts rushing near 400
LIMIT = 505                                 # the model's own limit is 510
MODELS = os.environ.get("MODELS_DIR", "/opt/models")
log = logging.getLogger("speech")

ABBR = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|St|No|Prof|vs|p|pp|Ltd|Co)\.|\b[A-Z]\.)[”\"']?$")
ENDS = ".,;:!?…—”"


def sentences(t):
    parts, last = [], 0
    for m in re.finditer(r"[.!?…]+[”\"')]*\s+(?=[“\"('‘]?[A-Z0-9—])", t):
        head = t[last:m.end()].rstrip()
        if ABBR.search(head): continue
        parts.append(head); last = m.end()
    tail = t[last:].strip()
    if tail: parts.append(tail)
    return parts


class Phonemizer:
    def __init__(self, british, texts, vocab, user_lexicon=None, slavic="auto"):
        from misaki import en, espeak
        logging.getLogger("phonemizer").setLevel(logging.ERROR)
        self.vocab = vocab
        self.g2p = en.G2P(trf=False, british=british, fallback=espeak.EspeakFallback(british=british))
        self.lex = Lexicon(self.g2p, texts, british, vocab, user_lexicon, slavic)
        self.cache = {}

    ELIDE = [(re.compile(r"\b([Tt])h'(?=\s)"), r"\1he"), (re.compile(r"(?<![\w'])[Tt]'(?=\s)"), "the"), (re.compile(r"(?<![\w'])[Oo]'(?=\s)"), "of"), (re.compile(r"\b([Ww])i'(?=\s)"), r"\1ith"),
             (re.compile(r"(?<![\w'])[Ii]'(?=\s)"), "in"), (re.compile(r"\b([Aa])n'(?=\s)"), r"\1nd"), (re.compile(r"\b([Hh])a'(?=\s)"), r"\1ave"), (re.compile(r"(\w)in'(?=\W|$)"), r"\1in"),
             (re.compile(r"(?<!\w)'([Tt]is|[Tt]was|[Tt]were|[Tt]would|[Tt]will|[Tt]isn't|[Tt]wasn't)\b"), r"\1"), (re.compile(r"\b[Ss]ha'n't\b"), "shan't")]

    def __call__(self, t):
        if t not in self.cache:
            x = self.lex.respelled(t)
            for a, b in self.ELIDE: x = a.sub(b, x)
            p = (self.g2p(x)[0] or "").replace("❓", "")
            p = "".join(c for c in p if c in self.vocab)
            self.cache[t] = re.sub(r"\s+", " ", p).strip()
        return self.cache[t]


class Planner:
    """chapter blocks -> chunks: {"ph": phonemes, "pause": seconds of silence after it, "text": source text}"""

    def __init__(self, ph): self.ph = ph

    def split_long(self, s, limit=HARD):
        if len(self.ph(s)) <= limit: return [s]
        best, mid = None, len(s) / 2
        for pat in (r"[;:—]\s?", r",”?\s", r"\s(?=and |but |which |who |that |because |or |when |where )", r"\s"):
            c = [m.end() for m in re.finditer(pat, s) if 0.2 < m.end() / len(s) < 0.8]
            if c: best = min(c, key=lambda x: abs(x - mid)); break
        if not best: return [s]
        return self.split_long(s[:best].strip(), limit) + self.split_long(s[best:].strip(), limit)

    def say(self, t, pause):
        """one short spoken line (titles, credits)"""
        t = t.strip()
        if t and t[-1] not in ".!?…”": t += "."
        return [dict(ph=self.ph(t), pause=pause, text=t)] if self.ph(t) else []

    def chunks(self, blocks):
        out, buf, txt, blen = [], "", "", 0

        def flush(p):
            nonlocal buf, txt, blen
            if buf: out.append(dict(ph=buf, pause=p, text=txt)); buf, txt, blen = "", "", 0
            elif out and p: out[-1]["pause"] = max(out[-1]["pause"], p)

        for i, (k, t) in enumerate(blocks):
            if k == "break": flush(1.8); continue
            if k == "gap": flush(1.0); continue
            if k == "head":
                flush(1.2); out += self.say(t, 1.0); continue
            if k == "verse":
                flush(0.6); p = self.ph(t)
                if not p: continue
                if p[-1] not in ENDS: p += ","
                buf, txt = p, t; flush(0.45); continue
            for s in (x for s in sentences(t) for x in self.split_long(s)):
                p = self.ph(s)
                if not re.search(r"[^\W_]", p): continue
                if p[-1] not in ENDS: p += "."
                if buf and (blen + len(p) > SOFT or blen >= TARGET): flush(0.32)
                buf, txt = (buf + " " + p, txt + " " + s) if buf else (p, s); blen = len(buf)
            # end of paragraph: short dialogue lines stay together, otherwise breathe here
            n = blocks[i + 1] if i + 1 < len(blocks) else None
            if not (blen < 110 and n and n[0] == "p" and len(n[1]) < 200): flush(0.7)
        flush(0.0)
        return out


def trim(w, lead=0.04, tail=0.10, db=-46):
    n = 240; m = len(w) // n
    if m < 3: return w
    e = np.sqrt((w[:m * n].reshape(m, n) ** 2).mean(1) + 1e-12)
    on = np.where(e > max(e.max() * 10 ** (db / 20), 1e-4))[0]
    if not len(on): return w[:0]
    a = max(0, int(on[0] * n - lead * SR)); b = min(len(w), int((on[-1] + 1) * n + tail * SR))
    x = w[a:b].copy(); f = min(240, len(x) // 4)
    if f: x[:f] *= np.linspace(0, 1, f, dtype=np.float32); x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return x


def load_vocab(models=MODELS):
    with open(os.path.join(models, "config.json"), encoding="utf-8") as f: return json.load(f)["vocab"]


def pick_device(want="auto"):
    """-> (device, explanation). Uses the GPU only if a small computation on it really works."""
    import torch
    if want == "cpu": return "cpu", "CPU (set in config)"
    if not torch.cuda.is_available():
        return "cpu", "CPU (no NVIDIA GPU is visible inside the container)"
    try:
        x = torch.randn(64, 64, device="cuda"); float((x @ x).sum()); torch.nn.functional.conv1d(torch.randn(1, 4, 64, device="cuda"), torch.randn(4, 4, 3, device="cuda")).sum().item()
        p = torch.cuda.get_device_properties(0)
        return "cuda", f"GPU: {p.name}, {p.total_memory / 2**30:.1f} GB"
    except Exception as e:
        return "cpu", f"CPU (the GPU {torch.cuda.get_device_name(0)} is visible but does not work: {str(e).splitlines()[0][:200]})"


class Synth:
    def __init__(self, device="auto", models=MODELS):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning); warnings.filterwarnings("ignore", category=FutureWarning)
        import torch
        from kokoro.model import KModel
        self.torch, self.models = torch, models
        self.device, self.where = pick_device(device)
        if self.device == "cpu": torch.set_num_threads(max(1, int(os.environ.get("CPU_THREADS") or os.cpu_count() or 1)))
        t0 = time.time()
        self.model = KModel(repo_id="hexgrad/Kokoro-82M", config=os.path.join(models, "config.json"), model=os.path.join(models, "kokoro-v1_0.pth")).to(self.device).eval()
        self.voices = {}
        log.info("model ready on %s in %.1f s", self.where, time.time() - t0)

    def voice(self, name):
        if name not in self.voices:
            self.voices[name] = self.torch.load(os.path.join(self.models, "voices", name + ".pt"), map_location="cpu", weights_only=True)
        return self.voices[name]

    def __call__(self, ph, voice, speed=1.0):
        ph = ph[:LIMIT]
        ref = self.voice(voice)[len(ph) - 1].to(self.device)
        for attempt in (1, 2):
            try:
                with self.torch.inference_mode(): w = self.model(ph, ref, speed)
                return w.detach().cpu().numpy().astype(np.float32).reshape(-1)
            except self.torch.cuda.OutOfMemoryError:
                self.torch.cuda.empty_cache()
                if attempt == 2: raise MemoryError("the GPU ran out of memory")
