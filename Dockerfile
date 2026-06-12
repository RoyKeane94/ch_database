# Build Tailwind CSS (source lives outside Django static/)
FROM node:20-slim AS css
WORKDIR /build
COPY com_house_man/package.json com_house_man/package-lock.json ./
RUN npm ci
COPY com_house_man/ .
RUN npm run build:css

# Django app
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY com_house_man/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY com_house_man/ .
COPY --from=css /build/core/static/css/styles.css ./core/static/css/styles.css

# collectstatic only needs Django settings, not production secrets
RUN DEBUG=True \
    DJANGO_SECRET_KEY=build-only \
    ALLOWED_HOSTS=localhost \
    COMPANIES_HOUSE_API_KEY=build \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "gunicorn com_house.wsgi --log-file - --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120"]
