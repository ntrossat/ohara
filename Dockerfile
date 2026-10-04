FROM node:24-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 PATH="/venv/bin:$PATH"
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ohara ./ohara
COPY --from=frontend /app/dist ./ohara/static
RUN useradd --create-home ohara && mkdir /data && chown ohara /data
USER ohara
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "ohara.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
