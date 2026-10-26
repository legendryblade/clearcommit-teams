# ClearCommit Teams API.
#
# Build:  docker build -t clearcommit-api .
# Run:    docker run -p 8770:8770 --env-file .env clearcommit-api
#
# Mount nothing: the API keeps no state on disk. Supabase PostgreSQL is the
# source of truth, so a container restart loses nothing.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY server ./server

# Supabase (or any PostgreSQL) is required for a hosted deployment.
ENV CLEARCOMMIT_SERVER_HOST=0.0.0.0 \
    CLEARCOMMIT_SERVER_PORT=8770

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8770/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "server"]
