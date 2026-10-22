FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system speakseed && adduser --system --ingroup speakseed speakseed \
    && mkdir -p /data/audio_cache && chown -R speakseed:speakseed /data
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=speakseed:speakseed app.py database.py migrations.py personalization.py security.py lessons.json ATTRIBUTION.md ./
COPY --chown=speakseed:speakseed migrations ./migrations
COPY --chown=speakseed:speakseed static ./static
COPY --chown=speakseed:speakseed tools ./tools
# This file is content-only and must be generated with
# `python tools/prepare_docker_seed.py` before building. The live database is
# excluded from the build context so accounts/progress cannot enter an image layer.
COPY --chown=speakseed:speakseed .docker-build/seed.db /app/seed.db
USER speakseed
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3)"
CMD ["sh", "-c", "python tools/docker_entrypoint.py && exec uvicorn app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1"]

