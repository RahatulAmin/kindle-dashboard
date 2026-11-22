FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run typecheck && npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/dashboard/backend
WORKDIR /opt/dashboard
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r backend/requirements.txt
COPY backend/app/ backend/app/
COPY backend/alembic/ backend/alembic/
COPY backend/alembic.ini backend/alembic.ini
COPY kindle/templates/ kindle/templates/
COPY --from=frontend /build/dist/ frontend/dist/
USER 1000:1000
EXPOSE 8765
CMD ["python", "-m", "app"]
