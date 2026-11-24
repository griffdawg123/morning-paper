FROM python:3.12-slim

# DejaVu for the generated cover; tzdata for zoneinfo.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    MORNING_PAPER_CONFIG=/config/paper.yml

# TrueNAS's `apps` user; the compose file can override.
USER 568:568
VOLUME ["/data"]
ENTRYPOINT ["morning-paper"]
CMD ["serve"]
