# --- 1) CSS: Tailwind CLI independente (sem Node) -----------------------------------------
FROM debian:bookworm-slim AS css
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /usr/local/bin/tailwindcss \
    https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
    && chmod +x /usr/local/bin/tailwindcss
WORKDIR /app
COPY tailwind.config.js ./
COPY static/src ./static/src
COPY templates ./templates
COPY apps ./apps
RUN tailwindcss -i static/src/input.css -o static/css/app.css --minify

# --- 2) Aplicacao --------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=css /app/static/css/app.css static/css/app.css
RUN useradd --create-home app && mkdir -p /app/media /app/staticfiles && chown -R app /app/media /app/staticfiles
USER app
# collectstatic nao acessa o banco; a chave abaixo vale so durante o build.
RUN DJANGO_SECRET_KEY=build-temporario python manage.py collectstatic --noinput
EXPOSE 8000
ENTRYPOINT ["sh", "scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
