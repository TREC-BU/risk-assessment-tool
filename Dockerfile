# Risk assessment Slack bot: Python + Typst + Arial.
# Helvetica Neue is not in the image (it's licensed with macOS); mount it at
# /app/fonts at run time. See docs/slack-bot.md.

FROM python:3.12-slim-bookworm

ARG TYPST_VERSION=0.15.1

# Arial comes from Microsoft's freely redistributable core fonts (Debian contrib).
RUN sed -i 's/^Components: main$/Components: main contrib/' /etc/apt/sources.list.d/debian.sources \
 && echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl xz-utils fontconfig ttf-mscorefonts-installer \
 && rm -rf /var/lib/apt/lists/*

RUN arch="$(uname -m)" \
 && curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${arch}-unknown-linux-musl.tar.xz" \
    | tar -xJ -C /tmp \
 && mv /tmp/typst-*/typst /usr/local/bin/typst \
 && rm -rf /tmp/typst-* \
 && typst --version

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir '.[bot]'
COPY risk-config.typ template.typ risk-assessment.typ ./

RUN useradd --create-home bot && mkdir -p /app/build /app/fonts && chown bot /app/build
USER bot

ENV TYPST_FONT_PATHS=/app/fonts \
    PYTHONUNBUFFERED=1
CMD ["risktool-slack"]
