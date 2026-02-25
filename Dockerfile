# Silicon Valet — multi-stage build
# Build: docker build -t silicon-valet:latest .

FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

LABEL maintainer="Silicon Valet"
LABEL description="Self-hosted agentic infrastructure intelligence"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
WORKDIR /app
COPY silicon_valet/ silicon_valet/
COPY pyproject.toml .

# Install the package itself (no deps, they're already installed)
RUN pip install --no-cache-dir --no-deps -e .

# Create non-root user
RUN useradd --create-home --shell /bin/bash valet
USER valet

# Data directory (mount PVC here)
ENV SV_DATA_DIR=/data/valet
ENV SV_WS_HOST=0.0.0.0
ENV SV_WS_PORT=7443

EXPOSE 7443

ENTRYPOINT ["python", "-m", "silicon_valet"]
