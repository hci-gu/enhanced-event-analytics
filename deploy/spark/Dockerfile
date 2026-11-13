FROM golang:1.27 AS pocketbase-build
WORKDIR /src
COPY pocketbase/go.mod pocketbase/go.sum ./
RUN go mod download
COPY pocketbase/ ./
RUN CGO_ENABLED=0 go build -o /pocketbase .

FROM debian:bookworm-slim AS pocketbase
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=pocketbase-build /pocketbase /usr/local/bin/pocketbase
CMD ["pocketbase", "serve", "--http=127.0.0.1:8090", "--dir=/data/pb_data"]

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-dev --no-install-project --extra CUDA
COPY --exclude=.env --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache backend/ ./
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
