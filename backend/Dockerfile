# ==============================================================================
# StockPilot PH — Production Multi-Stage Dockerfile (FastAPI Backend Server)
# Python 3.12-slim base with non-root security execution & healthcheck
# ==============================================================================

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for C-extensions (ReportLab, lxml, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies to wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


# ── Final Production Image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime system libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libjpeg62-turbo \
    zlib1g \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install wheels from builder stage
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Create non-privileged service user for runtime security
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy application source
COPY --chown=appuser:appgroup . /app

# Ensure data and reports directories exist with appropriate ownership
RUN mkdir -p /app/data/reports && \
    chown -R appuser:appgroup /app

USER appuser

# Expose FastAPI REST service port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Launch uvicorn decision server
CMD ["python", "-m", "uvicorn", "pse_quant.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
