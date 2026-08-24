# Linked Art Interoperability Repository — single-image deployment.
# The same image runs locally (fs backend) and in OpenStack (swift backend);
# only environment variables differ.
FROM python:3.11-slim

# Avoid interactive prompts and .pyc clutter; unbuffered logs for containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STORAGE_BACKEND=fs \
    DATA_DIR=/data/artifacts \
    INDEX_PATH=/data/index.sqlite3

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code, bundled context, frontend and sample data.
COPY app ./app
COPY sample_data ./sample_data

# Persist artifacts (fs mode) and the SQLite index on a mounted volume.
RUN mkdir -p /data/artifacts
VOLUME ["/data"]

EXPOSE 8000

# Uvicorn serves the FastAPI app; PORT can be overridden by the platform.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
