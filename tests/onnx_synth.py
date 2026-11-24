"""Developer aid: the same voice through onnxruntime, for trying the pipeline on a PC without PyTorch. Needs ONNX_MODEL and ONNX_VOICES."""
import json, os
import numpy as np, onnxruntime as ort
from app.speech import MODELS


class OnnxSynth:
    where = "onnxruntime (test)"
    device = "cpu"

    def __init__(self, device="auto"):
        o = ort.SessionOptions(); o.intra_op_num_threads = int(os.environ.get("CPU_THREADS", "5"))
        self.s = ort.InferenceSession(os.environ["ONNX_MODEL"], o, providers=["CPUExecutionProvider"]); self.v = np.load(os.environ["ONNX_VOICES"])
        with open(os.path.join(MODELS, "config.json"), encoding="utf-8") as f: self.vocab = json.load(f)["vocab"]

    def __call__(self, ph, voice, speed=1.0):
        ids = [self.vocab[c] for c in ph if c in self.vocab][:505]
        return np.asarray(self.s.run(["waveform"], {"input_ids": np.array([[0, *ids, 0]], dtype=np.int64), "style": self.v[voice][len(ids) - 1].astype(np.float32).reshape(1, 256), "speed": np.array([speed], dtype=np.float32)})[0], np.float32).reshape(-1)
