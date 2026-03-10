# Silicon Valet — multi-stage build
# Build: docker build -t silicon-valet:latest .

FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY silicon_valet/ silicon_valet/

# Install the package and all dependencies into /install prefix
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim

LABEL maintainer="Silicon Valet"
LABEL description="Self-hosted agentic infrastructure intelligence"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
WORKDIR /app
COPY silicon_valet/ silicon_valet/
COPY pyproject.toml .

# Create non-root user
RUN useradd --create-home --shell /bin/bash valet
USER valet

# Data directory (mount PVC here in k8s, or Docker volume)
ENV SV_DATA_DIR=/data/valet
ENV SV_OLLAMA_WORKER01=auto
ENV SV_OLLAMA_WORKER02=auto
ENV SV_ORCHESTRATOR_MODEL=qwen3:8b
ENV SV_CODER_MODEL=qwen2.5-coder:7b
ENV SV_EMBED_MODEL=nomic-embed-text
ENV SV_FAST_MODEL=phi4-mini
ENV SV_WS_HOST=0.0.0.0
ENV SV_WS_PORT=7443

EXPOSE 7443

ENTRYPOINT ["python", "-m", "silicon_valet"]
