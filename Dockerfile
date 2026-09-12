# Dockerfile for deploying Ollama Agents Web UI Dashboard
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    && rm -rf /var/lib/apt/lists/*

# Copy package build files
COPY dist/ollama_agents-0.6.0-py3-none-any.whl /app/

# Install built package
RUN pip install --no-cache-dir /app/ollama_agents-0.6.0-py3-none-any.whl

EXPOSE 8000

ENV OLLAMA_HOST=http://host.docker.internal:11434

CMD ["ollama-agents", "serve", "--host", "0.0.0.0", "--port", "8000"]
