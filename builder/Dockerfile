FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm libsdl2-2.0-0 libglib2.0-0 libpixman-1-0 zlib1g libsndio7.0 libpng16-16 \
    curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.local/share/uv/tools/pebble-tool/bin:${PATH}"

RUN uv tool install pebble-tool
RUN pebble sdk install latest

COPY watch.sh /watch.sh
RUN chmod +x /watch.sh

WORKDIR /build
CMD ["/watch.sh"]
