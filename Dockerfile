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

# Default to 8770 for local runs. A hosting platform injects PORT, which takes
# precedence in server/__main__.py, so no port is baked into the image.
ENV CLEARCOMMIT_SERVER_HOST=0.0.0.0

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import os,sys,urllib.request; p=os.environ.get('PORT') or '8770'; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "server"]
