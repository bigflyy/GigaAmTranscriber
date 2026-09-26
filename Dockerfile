FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1
COPY requirements-cpu.txt /tmp/requirements-cpu.txt
RUN sed '/^pyinstaller==/d' /tmp/requirements-cpu.txt > /tmp/runtime.txt \
    && pip install -r /tmp/runtime.txt
COPY gigaam /app/gigaam
COPY transcribe.py LICENSE /app/
ENTRYPOINT ["python", "/app/transcribe.py"]
CMD ["--help"]
