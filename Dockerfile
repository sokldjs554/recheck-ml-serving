# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY demo/package*.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca npm ci; else npm ci; fi
COPY demo/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r backend/requirements.txt; else pip install --no-cache-dir -r backend/requirements.txt; fi
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY --from=frontend /build/dist /app/web_static
RUN useradd -u 10001 -m runner && chown -R runner:runner /app
USER runner
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "scripts/serve_demo.py"]
