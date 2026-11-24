# Turns English books into audiobooks with Kokoro-82M. Uses an NVIDIA GPU when one works, otherwise the CPU.
#
# PyTorch is pinned to a CUDA 12.6 build on purpose: newer CUDA builds no longer run on GTX 10-series (Pascal) cards.
# The base is pinned by digest, so a rebuild reuses every large layer and an update is a small download.
FROM python:3.12-slim-bookworm@sha256:82836454a795d9d75549a9e157fd08dbac6c383292cf89e99f4248a97ce6b2ff

LABEL org.opencontainers.image.title="audiobook-maker" \
      org.opencontainers.image.description="Drop an English book into a folder, get a chaptered audiobook back" \
      org.opencontainers.image.version="1.1.1"

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tini \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 TOKENIZERS_PARALLELISM=false \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    MODELS_DIR=/opt/models DATA_DIR=/data HOME=/tmp

# large and rarely changing, so it gets its own layer
RUN pip install --index-url https://download.pytorch.org/whl/cu126 torch==2.7.1

COPY requirements.txt requirements-nodeps.txt /tmp/req/
RUN pip install --no-deps -r /tmp/req/requirements.txt -r /tmp/req/requirements-nodeps.txt

# the model and the voices are part of the image, so nothing is downloaded at run time
COPY fetch_models.py models.sha256 /tmp/req/
RUN python -I /tmp/req/fetch_models.py /opt/models /tmp/req/models.sha256

# on the CPU, PyTorch caches compiled code for every sentence length it meets, which grows to 4 GB and more; a small cache is just as fast
ENV ONEDNN_PRIMITIVE_CACHE_CAPACITY=8 LRU_CACHE_CAPACITY=8

RUN mkdir -p /opt/app /data && chown 568:568 /data
WORKDIR /opt/app

# Nothing may RUN below this line: the build then does not even have to download the layers above.
COPY --link app /opt/app/app

# 568 is the "apps" user on TrueNAS; override with "user:" in compose if your folders belong to someone else
USER 568:568
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=20s --start-period=60s CMD ["python", "-m", "app", "health"]
ENTRYPOINT ["tini", "--", "python", "-m", "app"]
CMD ["watch"]
