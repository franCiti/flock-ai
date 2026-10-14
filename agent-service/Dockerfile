# Image of the agent-service: the Agent Worker and the Ingestion Worker (plan section 7.5).
# Same image for both, with a different command. Build context: the repository root.
#
#   docker compose build agent

ARG PYTHON_IMAGE=python:3.12.15-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.24

FROM ${UV_IMAGE} AS uv

# --- Build: dependencies and the project, into a virtual environment ----------------------------
FROM ${PYTHON_IMAGE} AS build

# Root certificate of the corporate network, if the network inspects HTTPS (plan 7.8): every
# .crt in infra/corp-ca/ is trusted; with none, nothing changes.
COPY infra/corp-ca/ /usr/local/share/ca-certificates/corp/
RUN update-ca-certificates

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_EDITABLE=1

WORKDIR /app
# Dependencies first: they change less often than the code, so their layer is reused.
COPY agent-service/pyproject.toml agent-service/uv.lock agent-service/uv.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY agent-service/README.md ./
COPY agent-service/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime: Python, the virtual environment and the messages; no build tools ----------------
FROM ${PYTHON_IMAGE}

COPY infra/corp-ca/ /usr/local/share/ca-certificates/corp/
RUN update-ca-certificates \
    && useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin flock

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY agent-service/config /app/config
COPY agent-service/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MESSAGES_FILE=/app/config/messages.yaml \
    EMBEDDING_CACHE_DIR=/models \
    KNOWLEDGE_ROOT=/knowledge

# Starts as root only to prepare the certificates and the model cache, then runs the command as
# the unprivileged user "flock" (docker-entrypoint.sh).
ENTRYPOINT ["/bin/sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["flock-agent"]
