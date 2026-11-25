# Linked Art Interoperability Repository — single-image deployment.
# The same image runs locally (fs backend) and in OpenStack (swift backend);
# only environment variables differ.

# Build the React demo frontend; only the static bundle reaches the runtime image.
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

# Avoid interactive prompts and .pyc clutter; unbuffered logs for containers.
# REPOSITORY_DATA_DIR holds artifacts and the SQLite index; mount a volume there.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    REPOSITORY_DATA_DIR=/data \
    REPOSITORY_FRONTEND_DIR=/app/frontend/dist

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code, seeding script, sample data and the built frontend.
COPY app ./app
COPY scripts ./scripts
COPY sample_data ./sample_data
COPY --from=frontend /frontend/dist ./frontend/dist

# Persist artifacts (fs mode) and the SQLite index on a mounted volume.
RUN mkdir -p /data/artifacts
VOLUME ["/data"]

EXPOSE 8000

# Uvicorn serves the FastAPI app; PORT can be overridden by the platform.
# One worker only: the SQLite index serializes access with an in-process lock.
ENV PORT=8000 \
    FORWARDED_ALLOW_IPS=*
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]

# Isolated test image; no host data or credentials are needed.
FROM runtime AS test
COPY requirements-dev.txt requirements-swift.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["python", "-m", "pytest"]

# Keep the default image free of test dependencies and fixtures.
FROM runtime AS production
