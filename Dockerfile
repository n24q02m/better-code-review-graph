# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim-bookworm@sha256:bb73517d48bd32016e15eade0c009b2724ec3a025a9975b5cd9b251d0dcadb33
LABEL io.modelcontextprotocol.server.name="io.github.n24q02m/better-code-review-graph"
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"
# Make /app writable so appuser can create runtime state dirs
# (~/.mcp-relay/jwt-keys, config.enc, graph DB) — the runtime stage's
# WORKDIR + appuser HOME both resolve to /app, so without this the
# JWT issuer crashes at first authorize with FileNotFoundError.
RUN chown -R appuser:appuser /app
USER appuser
ENTRYPOINT ["better-code-review-graph", "serve"]
