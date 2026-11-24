"""One book, start to finish, inside its own folder under in-progress. Safe to stop and start again at any point.

  <job>/job.json      what is being made (source file, voice, stage)
  <job>/source/...    the original book
  <job>/plan.json     every sentence group to be read, written once
  <job>/chunks/...    finished audio pieces; existing ones are never made again
  <job>/result/...    the finished audiobook, moved to the output folder by the worker
"""
import errno, glob, json, logging, os, random, re, subprocess, sys, time
import numpy as np
from . import __version__, settings
from .author import Authors
from .readers import BookError, read_book
from .structure import build, looks_english, mark_title
from .speech import SR, Phonemizer, Planner, Synth, load_vocab, trim

log = logging.getLogger("job")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
HEADROOM = 0.7                              # some voices peak above full scale; the final volume is set when the book is put together
TAG = re.compile(r"\[\s*(male|female|[ab][fm]_[a-z]+)\s*\]", re.I)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path):
    with open(path, encoding="utf-8") as f: return json.load(f)


def safe_name(s, limit=110):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s.replace(": ", " - ").replace("; ", ", "))
    s = re.sub(r"\s+", " ", s).strip(" .")[:limit].strip(" .")
    return s or "Untitled"


hms = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02}:{int(s % 60):02}"


class Lazy:
    """loads the model only when something has to be said"""
    def __init__(self, make, device): self.make, self.device, self.real = make, device, None

    def get(self):
        if self.real is None: self.real = self.make(self.device)
        return self.real

    @property
    def where(self): return self.get().where

    def __call__(self, *a): return self.get()(*a)


class Job:
    def __init__(self, folder):
        self.dir = folder; self.path = os.path.join(folder, "job.json"); self.state = read_json(self.path); self.cfg = settings.load()
        self.last = 0.0

    def save(self, **kw): self.state.update(kw); write_json(self.path, self.state)

    def progress(self, text, done=0, total=0, eta=None, force=False, **more):
        if not force and time.time() - self.last < 5: return
        self.last = time.time(); pct = 100 * done / total if total else 0
        write_json(os.path.join(self.dir, "status.json"), dict(book=self.state.get("title") or self.state["file"], step=text, done=done, total=total, percent=round(pct, 1), eta_seconds=eta, updated=time.strftime("%Y-%m-%d %H:%M:%S"), **more))

    # ------------------------------------------------------------ 1. read the book and plan the narration
    def plan(self):
        p = os.path.join(self.dir, "plan.json")
        if os.path.exists(p): return read_json(p)
        self.progress("reading the book", force=True)
        src = os.path.join(self.dir, "source", self.state["file"]); stem = os.path.splitext(self.state["file"])[0]
        book = build(read_book(src), TAG.sub("", stem).replace("_", " ").strip())
        if not looks_english(book): raise BookError(f"the book does not seem to be in English (language: {book.language or 'not stated'}); only English is supported")
        gender, infos = Authors(settings.read_yaml("authors.yaml"), os.path.join(settings.CONFIG, "authors-cache.json"), self.cfg["lookup_author"]).book(book.authors)
        voice, why = self.pick_voice(stem, gender)
        self.save(title=book.title, author=book.author, voice=voice)
        log.info("%s by %s: %d chapters, voice %s (%s)", book.title, book.author, len(book.chapters), voice, why)
        self.progress("working out pronunciations", force=True)
        texts = [t for c in book.chapters for _, t in c.blocks] + [c.spoken for c in book.chapters] + [c.spoken_part for c in book.chapters] + [book.spoken_title, book.spoken_author, book.spoken_translator]
        ph = Phonemizer(voice[0] == "b", texts, load_vocab(), settings.read_yaml("lexicon.yaml"), self.cfg["slavic_names"]); L = Planner(ph)
        chapters, parts = [], len({c.group for c in book.chapters if c.group}) > 1
        for i, c in enumerate(book.chapters):
            ch = []
            if i == 0:
                ch += L.say(self.cfg["intro"].replace("{title}", book.spoken_title.rstrip(".")).replace("{author}", book.spoken_author.rstrip(".")), 1.0)
                if book.translator and self.cfg["intro_translator"]: ch += L.say(self.cfg["intro_translator"].replace("{translator}", book.spoken_translator.rstrip(".")), 1.0)
                if ch: ch[-1]["pause"] = 2.0
            if c.part: ch += L.say(c.spoken_part, 1.6)
            ch += L.say(c.spoken, 1.4) + L.chunks(c.blocks)
            if i == len(book.chapters) - 1 and self.cfg["outro"]:
                if ch: ch[-1]["pause"] = max(ch[-1]["pause"], 1.6)
                ch += L.say(self.cfg["outro"], 0.0)
            chapters.append(dict(title=mark_title(c, parts), chunks=ch))
            self.progress("working out pronunciations", i + 1, len(book.chapters))
        cover = ""
        if book.cover[:3] == b"\xff\xd8\xff": cover = "cover.jpg"
        elif book.cover[:8] == b"\x89PNG\r\n\x1a\n": cover = "cover.png"
        if cover:
            with open(os.path.join(self.dir, cover), "wb") as f: f.write(book.cover)
        plan = dict(title=book.title, author=book.author, translator=book.translator, voice=voice, voice_reason=why, gender=gender, authors=infos, cover=cover, copyrighted=book.copyrighted, speed=self.cfg["speed"],
                    chapters=chapters, skipped=book.skipped, shrunk=book.shrunk, source_chars=book.source_chars, kept_chars=book.kept_chars, notes_removed=book.notes_removed,
                    slavic=ph.lex.slavic, unknown=ph.lex.unknown(60), language=book.language, has_translator=bool(book.translator))
        if not any(c["chunks"] for c in chapters): raise BookError("nothing to read aloud was found in the book")
        write_json(p, plan)
        return plan

    def pick_voice(self, stem, gender):
        v = self.cfg["voices"]
        if self.state.get("voice"): return self.state["voice"], "chosen earlier for this book"
        tag = TAG.search(stem); t = tag.group(1).lower() if tag else ""
        if t and "_" in t:
            if t in settings.available_voices(): return t, "named in the file name"
            raise BookError(f"the file name asks for the voice '{t}', which does not exist")
        if t: gender = t
        pool = v.get(gender) or (v["male"] + v["female"])
        why = f"picked at random from the {gender} voices" + (" (file name)" if t else "") if v.get(gender) else "picked at random from all voices, because the author's gender is not known"
        return random.SystemRandom().choice(pool), why

    # ------------------------------------------------------------ 2. narrate
    def chunk_path(self, c, j): return os.path.join(self.dir, "chunks", f"{c:04}", f"{j:05}.npy")

    @staticmethod
    def pcm16(audio): return (np.clip(audio * HEADROOM, -1, 1) * 32767).astype(np.int16)

    def store(self, path, audio):
        tmp = path[:-4] + ".tmp.npy"
        np.save(tmp, self.pcm16(audio)); os.replace(tmp, path)

    def narrate(self, plan, synth):
        todo = [(c, j, x) for c, ch in enumerate(plan["chapters"]) for j, x in enumerate(ch["chunks"]) if not os.path.exists(self.chunk_path(c, j))]
        total = sum(len(ch["chunks"]) for ch in plan["chapters"]); done = total - len(todo)
        for c in range(len(plan["chapters"])): os.makedirs(os.path.join(self.dir, "chunks", f"{c:04}"), exist_ok=True)
        t0, chars, left, audio = time.time(), 0, sum(len(x["ph"]) for *_, x in todo), 0.0
        if todo: log.info("narrating %d of %d pieces on %s", len(todo), total, synth.where)
        for n, (c, j, x) in enumerate(todo):
            w = self.speak(synth, x["ph"], plan); self.store(self.chunk_path(c, j), w)
            chars += len(x["ph"]); audio += len(w) / SR; el = time.time() - t0
            eta = el / chars * (left - chars)
            self.progress(f"narrating ({plan['voice']}, {synth.where}, {audio / max(el, 1e-6):.1f}x real time)", done + n + 1, total, round(eta), speed=round(audio / max(el, 1e-6), 1), device=synth.where)
            if (n + 1) % 200 == 0: log.info("%s: %d/%d pieces, %.1fx real time, about %s left", plan["title"], done + n + 1, total, audio / el, hms(eta))
        if todo: self.save(synth_seconds=round(self.state.get("synth_seconds", 0) + time.time() - t0), device=synth.where)

    def speak(self, synth, ph, plan, depth=0):
        try: return trim(synth(ph, plan["voice"], plan["speed"]))
        except MemoryError:
            if depth >= 3 or len(ph) < 60: raise
            return np.concatenate([self.speak(synth, p, plan, depth + 1) for p in self.halves(ph)])

    @staticmethod
    def halves(ph):
        mid = len(ph) / 2
        for pat in (r"[.!?…]”?\s", r"[;:—]\s?", r",”?\s", r"\s"):
            cut = [m.end() for m in re.finditer(pat, ph) if 0.15 < m.end() / len(ph) < 0.85]
            if cut:
                k = min(cut, key=lambda x: abs(x - mid)); return [ph[:k].strip(), ph[k:].strip()]
        return [ph]

    # ------------------------------------------------------------ 3. check every piece and redo the odd ones
    @staticmethod
    def measure(a):
        a = a.astype(np.float32) / 32768; n = 1200; m = len(a) // n
        e = np.sqrt((a[:m * n].reshape(m, n) ** 2).mean(1) + 1e-12) if m else np.array([0.0])
        run = best = 0
        for q in e < max(float(e.max()) * 0.01, 1e-4): run = run + 1 if q else 0; best = max(best, run)
        return dict(sec=len(a) / SR, clip=int((np.abs(a) > 0.999).sum()), gap=best * n / SR, rms=float(20 * np.log10(np.sqrt((a ** 2).mean()) + 1e-9)) if len(a) else -99.0)

    @staticmethod
    def faults(n, m, rate, rms):
        out = []
        if n >= 40 and not rate * 0.65 < n / max(m["sec"], 1e-3) < rate * 1.45: out.append("odd pace")
        if m["sec"] < 0.15: out.append("empty")
        if m["clip"] > 3: out.append("clipping")
        if m["gap"] > 1.6: out.append("long gap")
        if n >= 40 and abs(m["rms"] - rms) > 6: out.append("odd level")
        return out

    def check(self, plan, synth):
        self.progress("checking the audio", force=True)
        rows = [(c, j, x, self.measure(np.load(self.chunk_path(c, j)))) for c, ch in enumerate(plan["chapters"]) for j, x in enumerate(ch["chunks"])]
        big = [r for r in rows if len(r[2]["ph"]) >= 40] or rows
        rate = float(np.median([len(r[2]["ph"]) / max(r[3]["sec"], 1e-3) for r in big])); rms = float(np.median([r[3]["rms"] for r in big]))
        fixed, left = 0, []
        for c, j, x, m in rows:
            bad = self.faults(len(x["ph"]), m, rate, rms)
            if not bad: continue
            parts = self.halves(x["ph"])
            w = np.concatenate([np.concatenate([self.speak(synth, p, plan), np.zeros(int(0.2 * SR), np.float32)]) for p in parts])
            m2 = self.measure(self.pcm16(w)); still = self.faults(len(x["ph"]), m2, rate, rms)
            if len(still) < len(bad): self.store(self.chunk_path(c, j), w)
            if still: left.append(dict(chapter=plan["chapters"][c]["title"], problem=", ".join(still if len(still) < len(bad) else bad), text=x["text"][:160]))
            else: fixed += 1
        log.info("%s: %d pieces checked, %d redone, %d still odd", plan["title"], len(rows), fixed, len(left))
        return dict(pieces=len(rows), redone=fixed, odd=left, rate=round(rate, 1), rms=round(rms, 1))

    # ------------------------------------------------------------ 4. build the audiobook
    def pcm(self, plan, c, last):
        ch = plan["chapters"][c]["chunks"]
        for j, x in enumerate(ch):
            yield np.load(self.chunk_path(c, j)).tobytes()
            yield bytes(2 * int(SR * (x["pause"] if j < len(ch) - 1 else (4.0 if last else 2.8))))

    def package(self, plan):
        self.progress("building the audiobook file", force=True)
        out_dir = os.path.join(self.dir, "result"); os.makedirs(out_dir, exist_ok=True)
        for f in glob.glob(os.path.join(glob.escape(out_dir), "*")): os.remove(f)
        out = os.path.join(out_dir, safe_name(plan["title"]) + ".m4b"); chs = [c for c in range(len(plan["chapters"])) if plan["chapters"][c]["chunks"]]
        marks, pos = [], 0
        for c in chs:
            ch = plan["chapters"][c]["chunks"]; n = 0
            for j, x in enumerate(ch):
                n += np.load(self.chunk_path(c, j), mmap_mode="r").shape[0] + int(SR * (x["pause"] if j < len(ch) - 1 else (4.0 if c == chs[-1] else 2.8)))
            marks.append((pos, pos + n, plan["chapters"][c]["title"])); pos += n
        # loudness of about 20 minutes spread over the book -> one gain for everything, which keeps the voice's own dynamics
        allc = [(c, j) for c in chs for j in range(len(plan["chapters"][c]["chunks"]))]
        raw = b"".join(np.load(self.chunk_path(*x)).tobytes() + bytes(2 * int(0.3 * SR)) for x in allc[::max(1, len(allc) // 120)])
        r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", "-af", "highpass=f=60,ebur128", "-f", "null", "-"], input=raw, capture_output=True)
        found = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode("utf-8", "replace")); gain = min(20.0, self.cfg["loudness"] - float(found[-1])) if found and float(found[-1]) > -60 else 0.0
        esc = lambda s: re.sub(r"([=;#\\\n])", r"\\\1", s)
        meta = [";FFMETADATA1", "title=" + esc(plan["title"]), "artist=" + esc(plan["author"]), "album_artist=" + esc(plan["author"]), "album=" + esc(plan["title"]), "composer=" + esc(f"AI narration (Kokoro-82M, {plan['voice']})"), "genre=Audiobook",
                "comment=" + esc((f"Translated by {plan['translator']}. " if plan["translator"] else "") + "Narrated by a synthetic voice.")]
        for a, b, t in marks: meta += ["[CHAPTER]", f"TIMEBASE=1/{SR}", f"START={a}", f"END={b}", "title=" + esc(t)]
        mf = os.path.join(self.dir, "meta.txt")
        with open(mf, "w", encoding="utf-8") as f: f.write("\n".join(meta) + "\n")
        cmd = [FFMPEG, "-y", "-hide_banner", "-nostats", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", "-i", mf]
        if plan["cover"]: cmd += ["-i", os.path.join(self.dir, plan["cover"])]
        cmd += ["-map", "0:a"] + (["-map", "2:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"] if plan["cover"] else [])
        cmd += ["-map_metadata", "1", "-map_chapters", "1", "-af", f"highpass=f=60,volume={gain:.2f}dB,alimiter=limit=0.70:level=false", "-c:a", "aac", "-b:a", self.cfg["bitrate"], "-ar", str(SR), "-movflags", "+faststart", "-f", "mp4", out]
        with open(os.path.join(self.dir, "ffmpeg.log"), "w+", encoding="utf-8", errors="replace") as errlog:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errlog)
            try:
                for n, c in enumerate(chs):
                    for b in self.pcm(plan, c, c == chs[-1]): p.stdin.write(b)
                    self.progress("building the audiobook file", n + 1, len(chs))
                p.stdin.close()
            except BrokenPipeError: pass
            rc = p.wait(); errlog.seek(0); err = errlog.read()
        if rc: raise RuntimeError("ffmpeg could not build the audiobook: " + err.strip()[-600:])
        return out, marks, pos / SR, gain

    # ------------------------------------------------------------ 5. decode the finished file completely and compare
    def verify(self, out, marks, seconds):
        self.progress("checking the finished file", force=True)
        info = subprocess.run([FFMPEG, "-hide_banner", "-i", out], capture_output=True).stderr.decode("utf-8", "replace")
        chapters = len(re.findall(r"Chapter #\d+:\d+: start", info))
        r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", out, "-map", "0:a", "-af", "astats=measure_perchannel=none:measure_overall=Peak_level+Number_of_samples", "-f", "null", "-"], capture_output=True)
        text = r.stderr.decode("utf-8", "replace")
        n = re.findall(r"Number of samples: (\d+)", text); peak = re.findall(r"Peak level dB: (-?[\d.]+|-?inf)", text)
        dur = int(n[-1]) / SR if n else 0.0; problems = []
        if r.returncode or re.search(r"Error while decoding|Invalid data|corrupt", text): problems.append("the file did not decode cleanly")
        if abs(dur - seconds) > 1.0: problems.append(f"length is {dur:.1f} s, expected {seconds:.1f} s")
        if chapters != len(marks): problems.append(f"{chapters} chapter marks, expected {len(marks)}")
        return dict(duration=round(dur, 1), chapters=chapters, peak=f"{float(peak[-1]):.1f}" if peak else "?", problems=problems)

    # ------------------------------------------------------------ 6. report
    def report(self, plan, qa, ver, marks, out):
        L = [f"{plan['title']}", f"by {plan['author']}" + (f", translated by {plan['translator']}" if plan["translator"] else ""), "",
             f"Length     {hms(ver['duration'])}, {ver['chapters']} chapters, {os.path.getsize(out) / 1e6:.0f} MB",
             f"Voice      {plan['voice']} ({plan['voice_reason']})"]
        for a in plan["authors"]: L.append(f"Author     {a['name']}: {a['gender'] or 'gender not known'} ({a['source']}" + (f", {a['id']}" if a.get("id") else "") + ")" + (f", born {a['born']}" if a.get("born") else "") + (f", died {a['died']}" if a.get("died") else ""))
        L += [f"Made with  audiobook-maker {__version__}, Kokoro-82M, {self.state.get('device', '')}, {hms(self.state.get('synth_seconds', 0))} of narration time", "",
              "CHECKS", f"  Text: {100 * plan['kept_chars'] / max(plan['source_chars'], 1):.1f}% of the book's letters are narrated; the rest is listed under NOT READ.",
              f"  Audio: {qa['pieces']} pieces, {qa['redone']} redone automatically, {len(qa['odd'])} still look odd.",
              f"  File: {'; '.join(ver['problems']) if ver['problems'] else 'decodes cleanly, length and chapter marks are right'}. Peak {ver['peak']} dB.",
              "  Nobody has listened to it. These checks cannot hear a mispronounced word."]
        for o in qa["odd"]: L.append(f"    - {o['chapter']}: {o['problem']}: {o['text']}")
        for t, n in plan["shrunk"]: L.append(f"    - lost {n} letters in cleaning: {t}")
        L += ["", "RIGHTS (check before publishing)"]
        if plan["copyrighted"]: L.append("  !! The book file says it is STILL IN COPYRIGHT. Do not publish it without permission.")
        died = [a.get("died") for a in plan["authors"] if a.get("died")]; now = time.localtime().tm_year
        if died and len(died) == len(plan["authors"]):
            y = max(died) + 71
            L.append(f"  Author(s) died by {max(died)}: the original text is out of copyright in life+70 countries " + (f"since {y}." if y <= now else f"only from {y}."))
        else: L.append("  The author's year of death is not known here; check it.")
        if plan["has_translator"]: L.append(f"  This is a translation: {plan['translator']}'s own copyright counts too. Check when the translator died.")
        L.append("  “Public domain in the USA” (the usual Gutenberg status) does not cover other countries.")
        L += ["", "NOT READ"] + ([f"  - {w} ({n} letters)" for w, n in plan["skipped"]] or ["  - nothing beyond page furniture"])
        if plan["notes_removed"]: L.append(f"  - {plan['notes_removed']} footnote marks")
        L += ["", "WORDS READ BY GUESSWORK (add fixes to config/lexicon.yaml)", "  " + (", ".join(f"{w} ({n})" for w, n in plan["unknown"]) or "none")]
        L += ["", "CHAPTERS"] + [f"  {hms(a / SR)} {t}" for a, _, t in marks]
        with open(os.path.join(self.dir, "result", "report.txt"), "w", encoding="utf-8") as f: f.write("\n".join(L) + "\n")

    def run(self, make_synth=Synth):
        plan = self.plan(); self.save(stage="narrate")
        synth = Lazy(make_synth, self.cfg["device"])
        self.narrate(plan, synth); qa = self.check(plan, synth)
        self.save(stage="package"); out, marks, seconds, gain = self.package(plan)
        ver = self.verify(out, marks, seconds)
        if ver["problems"]: raise RuntimeError("the finished file failed its check: " + "; ".join(ver["problems"]))
        self.report(plan, qa, ver, marks, out)
        self.save(stage="done", length=ver["duration"]); self.progress("finished", 1, 1, 0, force=True)
        log.info("%s: finished, %s, %d chapters", plan["title"], hms(ver["duration"]), ver["chapters"])


def main(folder):
    """exit codes: 0 done, 3 the book cannot be narrated (no point in trying again), 4 the server has a problem (wait), anything else: try again"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    try: Job(folder).run(); return 0
    except BookError as e:
        with open(os.path.join(folder, "error.txt"), "w", encoding="utf-8") as f: f.write(str(e) + "\n")
        log.error("cannot narrate this book: %s", e); return 3
    except Exception as e:
        log.exception("the job failed")
        if isinstance(e, OSError) and e.errno in (errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EACCES, errno.EPERM):
            log.error("this is a problem with the server, not with the book: %s", e); return 4
        with open(os.path.join(folder, "error.txt"), "w", encoding="utf-8") as f: f.write(f"{type(e).__name__}: {e}\n")
        return 1
