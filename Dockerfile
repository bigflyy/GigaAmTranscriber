FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# cpu by default; use --build-arg TORCH_VARIANT=cu124 for NVIDIA CUDA.
ARG TORCH_VARIANT=cpu
RUN case "$TORCH_VARIANT" in cpu|cu124) ;; *) echo "Expected cpu or cu124"; exit 1 ;; esac \
    && pip install --index-url https://download.pytorch.org/whl/${TORCH_VARIANT} torch==2.5.1 torchaudio==2.5.1
COPY requirements-cpu.txt /tmp/requirements-cpu.txt
RUN sed '/^pyinstaller==/d' /tmp/requirements-cpu.txt > /tmp/runtime.txt \
    && pip install -r /tmp/runtime.txt
COPY gigaam /app/gigaam
COPY transcribe.py model_catalog.py LICENSE /app/
ENTRYPOINT ["python", "/app/transcribe.py"]
CMD ["--help"]
