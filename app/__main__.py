"""python -m app [watch | check | voices | sample <voice> | preview <book> | health]"""
import os, sys, time


def check():
    """is the GPU used, and how fast is it?"""
    import numpy as np, torch
    from . import settings
    from .speech import MODELS, SR, Phonemizer, Synth, load_vocab
    print("PyTorch", torch.__version__, "| built for CUDA", torch.version.cuda, "| GPU kernels:", " ".join(torch._C._cuda_getArchFlags().split()) if torch.version.cuda else "none")
    print("GPU visible in the container:", torch.cuda.device_count())
    s = Synth(settings.load()["device"]); print("Running on", s.where)
    ph = Phonemizer(False, [], load_vocab())("It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness, it was the epoch of belief, it was the epoch of incredulity.")
    s(ph, "am_michael"); t = time.time(); n = 0
    for _ in range(5): n += len(s(ph, "am_michael"))
    print(f"Speed: {n / SR / (time.time() - t):.1f}x real time (a 10-hour book takes about {10 / (n / SR / (time.time() - t)):.1f} hours)")
    if s.device == "cuda": print(f"GPU memory used: {torch.cuda.max_memory_allocated() / 2**20:.0f} MB")


def sample(voice):
    import numpy as np, subprocess
    from . import settings
    from .speech import SR, Phonemizer, Planner, Synth, load_vocab, trim
    from .job import FFMPEG
    T = [("p", "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife."),
         ("p", "“My dear Mister Bennet,” said his lady to him one day, “have you heard that Netherfield Park is let at last?”"), ("p", "Mister Bennet replied that he had not.")]
    s = Synth(settings.load()["device"]); L = Planner(Phonemizer(voice[0] == "b", [t for _, t in T], load_vocab()))
    w = np.concatenate([np.concatenate([trim(s(c["ph"], voice)), np.zeros(int(c["pause"] * SR), np.float32)]) for c in L.chunks(T)])
    out = os.path.join(settings.OUTPUT, f"sample_{voice}.mp3")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-b:a", "96k", out], input=w.tobytes(), check=True); print(out)


def preview(path):
    """what would be read and what would be left out, without narrating anything"""
    from .readers import read_book, BookError
    from .structure import build, looks_english, mark_title
    try: b = build(read_book(path), os.path.splitext(os.path.basename(path))[0])
    except BookError as e: print("This book cannot be narrated:", e); return 1
    parts = len({c.group for c in b.chapters if c.group}) > 1
    print(f"{b.title}, by {b.author}" + (f", translated by {b.translator}" if b.translator else "") + f" | English: {'yes' if looks_english(b) else 'NO'} | {100 * b.kept_chars / max(b.source_chars, 1):.1f}% of the letters are read")
    for what, n in b.skipped: print(f"  not read: {what} ({n} letters)")
    for i, c in enumerate(b.chapters, 1): print(f"  {i:3} {mark_title(c, parts)}  [{sum(len(t) for _, t in c.blocks)} characters] {next((t for k, t in c.blocks if k == 'p'), '')[:60]}")


def main(a):
    cmd = a[0] if a else "watch"
    if cmd == "watch":
        from .worker import watch
        return watch()
    if cmd == "job":
        from .job import main as job
        return job(a[1])
    if cmd == "health":
        try: return 0 if time.time() - os.path.getmtime(os.environ.get("HEARTBEAT", "/tmp/heartbeat")) < 180 else 1
        except OSError: return 1
    if cmd == "check": return check()
    if cmd == "sample" and len(a) > 1: return sample(a[1])
    if cmd == "preview" and len(a) > 1: return preview(a[1])
    if cmd == "voices":
        from .settings import available_voices
        print("\n".join(available_voices())); return 0
    print(__doc__); return 2


if __name__ == "__main__": sys.exit(main(sys.argv[1:]) or 0)
