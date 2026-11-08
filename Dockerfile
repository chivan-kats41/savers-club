FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r -u 10001 app && mkdir -p /app/media /app/private_media /app/staticfiles /app/logs && chown -R app /app
USER app
# collectstatic needs a syntactically valid key but never uses it at runtime
RUN SECRET_KEY=build-only-$(python -c "import secrets;print(secrets.token_hex(32))") DB_NAME=x DB_USER=x DB_PASSWORD=x \
    DJANGO_SETTINGS_MODULE=config.settings.production python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--access-logfile", "-"]
