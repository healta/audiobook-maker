# Third-party software in the image

This project's own code is in `app/`. The image also contains the following, under their own licences. Licence texts are inside the image, next to each package (`/usr/local/lib/python3.12/site-packages/*.dist-info`, `/usr/share/doc/*/copyright`).

| Component | Used for | Licence |
|---|---|---|
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) model and voices (revision f3ff357) | the voices | Apache-2.0 |
| [kokoro](https://github.com/hexgrad/kokoro), [misaki](https://github.com/hexgrad/misaki) | running the model, pronunciation | Apache-2.0 |
| [phonemizer-fork](https://pypi.org/project/phonemizer-fork/) | pronunciation of unknown words | **GPL-3.0-or-later** |
| [eSpeak NG](https://github.com/espeak-ng/espeak-ng) (through espeakng-loader) | pronunciation of unknown words | **GPL-3.0-or-later** |
| [FFmpeg](https://ffmpeg.org) (Debian build) | building the audiobook file | **GPL-2.0-or-later** |
| [PyTorch](https://pytorch.org) | running the model | BSD-3-Clause |
| NVIDIA CUDA, cuDNN and related libraries | running the model on the GPU | **NVIDIA proprietary**, redistributable only under NVIDIA's terms |
| [num2words](https://github.com/savoirfairelinux/num2words) | reading numbers | LGPL |
| [spaCy](https://spacy.io), en_core_web_sm | sentence analysis | MIT |
| transformers, tokenizers, huggingface-hub, safetensors | running the model | Apache-2.0 |
| lxml, NumPy, PyYAML, loguru and other small packages | | BSD, MIT, Apache-2.0, MPL-2.0, PSF |
| Debian, Python | base system | various free licences |

## Source code of the GPL parts

They are unmodified. The source of the Debian packages (FFmpeg and others) is at https://sources.debian.org, under the version shown by `dpkg -l` in the image. The source of the Python packages is on PyPI, at the versions in `requirements.txt` and `requirements-nodeps.txt`; espeakng-loader contains eSpeak NG, whose source is at https://github.com/espeak-ng/espeak-ng. If a link stops working, please open an issue.

This project's own code is under the BSD Zero Clause License (see LICENSE). Because it is used together with a GPL-3.0 package (phonemizer), the image as a whole can be passed on under the terms of GPL-3.0, apart from NVIDIA's libraries, which are only passed on unchanged as part of PyTorch.

This is a summary for orientation, not legal advice.
