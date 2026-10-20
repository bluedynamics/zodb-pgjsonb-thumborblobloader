FROM python:3.13-trixie

# Python package version of the checkout; .git is not in the build context.
ARG LOADER_VERSION=0.0.0

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Thumbor 7.8.0 passes float sizes (--resize 70x70.0); gifsicle 1.98 rejects
# them and every animated GIF would fail with a 500 (thumbor/thumbor#1933).
# Fail the build instead; drop the check once a Thumbor release has the fix.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gifsicle \
    && rm -rf /var/lib/apt/lists/* \
    && gifsicle --version | head -1 | grep -E "Gifsicle 1\.(8[0-9]|9[0-7])$"

RUN uv pip install --system --no-cache \
    "thumbor>=7.0" \
    "opencv-python-headless>=4.8"

# The loader comes from this checkout, not from PyPI: the image is built while
# the release is still uploading, and an unchanged install line let the layer
# cache ship an older loader under a newer tag.
COPY pyproject.toml README.md LICENSE.txt /src/
COPY src /src/src
RUN SETUPTOOLS_SCM_PRETEND_VERSION="${LOADER_VERSION}" \
    uv pip install --system --no-cache "/src[s3]"

COPY thumbor.conf /etc/thumbor.conf

# One malloc arena per thread fragments memory with large image buffers.
ENV MALLOC_ARENA_MAX=2

EXPOSE 8888

CMD ["thumbor", "--conf=/etc/thumbor.conf"]
