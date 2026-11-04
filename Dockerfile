# GigaAM Transcriber command-line image on ONNX Runtime. No PyTorch in the final image.
#
# Stage 1 downloads the GigaAM v3 checkpoints and the Silero VAD model and exports
# them to ONNX with the repository's own tools (CPU PyTorch, build time only).
# Stage 2 holds just Python, numpy, ONNX Runtime, ffmpeg, the app and the models,
# so the image works offline.
#
#   docker build -t gigaam-transcriber:cpu .
#   docker build --build-arg ORT_VARIANT=cuda -t gigaam-transcriber:cuda .

FROM python:3.12-slim AS export
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0
COPY requirements-export.txt /tmp/
RUN grep -v -E '^(torch|torchaudio)' /tmp/requirements-export.txt > /tmp/export.txt \
    && pip install -r /tmp/export.txt
COPY gigaam /src/gigaam
COPY tools/export_models.py tools/make_silero_scan.py /src/tools/
RUN python tools/export_models.py v3_e2e_rnnt v3_e2e_ctc --out /models \
    && python tools/make_silero_scan.py --out /models/silero_vad_scan.onnx \
    && rm -rf /root/.cache

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# cpu: onnxruntime. cuda: onnxruntime-gpu with the CUDA 12 and cuDNN 9 libraries from PyPI,
# for NVIDIA GPUs through `docker run --gpus all`; it falls back to the CPU without a GPU.
ARG ORT_VARIANT=cpu
RUN case "$ORT_VARIANT" in \
      cpu) pip install numpy==2.5.4 onnxruntime==1.23.0 ;; \
      cuda) pip install numpy==2.5.4 "onnxruntime-gpu[cuda,cudnn]==1.23.0" ;; \
      *) echo "ORT_VARIANT must be cpu or cuda" && exit 1 ;; \
    esac
WORKDIR /app
COPY --from=export /models /app/models
COPY gigaam_app /app/gigaam_app
COPY LICENSE THIRD_PARTY_NOTICES.md gigaam-config.example.json /app/
# Settings and outputs live in the mounted folder, not in the image.
ENV GIGAAM_MODELS=/app/models PYTHONPATH=/app
WORKDIR /data
ENTRYPOINT ["python", "-m", "gigaam_app.cli"]
CMD ["--help"]
