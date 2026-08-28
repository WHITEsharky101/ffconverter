# FFConverter runtime image.
#
# Base: jrottenberg/ffmpeg:9.0-ubuntu2404
#   - ffmpeg/ffprobe 9.0.1 with --enable-libx265 --enable-libvmaf --enable-libzimg
#   - entrypoint "ffmpeg", binaries in /usr/local/bin, no Python
#
# The converter driver runs INSIDE this image (the media is mounted into the
# container; the host has no access to it), so ffmpeg/ffprobe always resolve
# to the pinned 9.0.1 binaries on PATH — no version drift between CRF
# samples, VMAF measurements and the final encode.
FROM jrottenberg/ffmpeg:9.0-ubuntu2404

ENV TZ=Europe/Moscow

# python3        — the converter driver itself
# python3-rarfile— .rar/.zip font archive extraction (fonts.py)
# unrar          — RARLAB unrar 7.x: rarfile's external backend. anime libs
#                  ship SOLID .rar archives (Fonts.rar) which unrar-free
#                  CANNOT extract (verified: "solid archive support
#                  unavailable"); RARLAB unrar handles them.
# tzdata         — TZ=Europe/Moscow
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-rarfile unrar tzdata \
    && rm -rf /var/lib/apt/lists/*

# Code is baked in: the image pins code + ffmpeg version together.
WORKDIR /code
COPY . /code

# Runtime data files live in the named volume mounted at /code/data
# (docker-compose.yml: ffconv_data). The symlinks below make the code's
# code-relative paths (CONVERTLIST_PATH, settings.json) and the CWD-relative
# streams_data.json resolve into that volume, so they survive
# `docker compose run --rm`. Targets are created on first write (a dangling
# symlink is intentional: an empty seeded streams_data.json would make the
# first start print "Ошибка при загрузке данных" before the wizard).
RUN mkdir -p /code/data \
    && ln -s data/convertlist.txt /code/convertlist.txt \
    && ln -s data/streams_data.json /code/streams_data.json \
    && ln -s data/settings.json /code/settings.json

# Default run: the conversion step (auto-runs the config wizard on first start).
# Override for one-off commands, e.g.:
#   docker run --rm --entrypoint ffprobe ffconverter:local -version
#   docker run --rm --entrypoint python3 ffconverter:local /code/create_ffmpeg_config.py
ENTRYPOINT ["python3", "/code/ffmpeg_converter.py"]
