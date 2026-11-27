#!/bin/bash
# Linux release build in WSL (Ubuntu 24.04), with the smoke tests on the models that the
# Windows app downloaded. Run it from Windows, through the work queue, for example:
#   MSYS_NO_PATHCONV=1 agg-queue.exe run --kind build --what "GigaAM Linux app build with smoke tests" \
#     -- wsl.exe -d Ubuntu --exec bash /mnt/c/MyProjects/GigaAmTranscriber/tools/wsl_build.sh \
#     --out /home/bigfly/gigaam-build-080 --release /mnt/c/MyProjects/GigaAmTranscriber/build/v0.8.0/release
# (MSYS_NO_PATHCONV=1 only from Git Bash: it would rewrite the /mnt/c argument.)
# Build Windows first into the same release folder: the Linux build adds its licences beside
# the windows/ ones in THIRD_PARTY_LICENSES.zip. Other arguments go to tools/build_linux.py.
#
# Needs: the venv ~/.venvs/gigaam-build (system Python 3.12, requirements-build.txt), the
# patched whisper.cpp in third_party/whisper.cpp/linux-x64 (tools/build_whisper_cpp.py), and
# a short Russian speech file (default build/release-test/lab-clip.mp3, gitignored).
set -e
cd "$(dirname "$0")/.."

# The Windows app's download folder: Whisper, faster-whisper and the speaker models.
MODELS="${GIGAAM_TEST_MODELS:-/mnt/c/Users/User/AppData/Local/GigaAmTranscriber/models}"
CLIP="${GIGAAM_TEST_CLIP:-build/release-test/lab-clip.mp3}"

exec ~/.venvs/gigaam-build/bin/python tools/build_linux.py \
    --speech "$CLIP" --whisper-audio "$CLIP" \
    --whisper-model "$MODELS/whisper_large_v3_turbo_q5_0" \
    --fast-whisper-model "$MODELS/faster_whisper_large_v3_turbo_int8" \
    --speaker-model "$MODELS/speakers_community1" \
    "$@"
