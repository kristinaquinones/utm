FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY requirements-e2e.txt .
COPY pytest.ini .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY alembic.ini .
COPY alembic ./alembic
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

# The entrypoint runs `alembic upgrade head` before the server starts.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# --proxy-headers + --forwarded-allow-ips=* so uvicorn trusts Caddy's
# X-Forwarded-Proto and builds https:// URLs (url_for static assets, redirects).
# Caddy is the only thing that reaches this container (port 8000 is not published),
# so trusting all forwarded IPs is safe here.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
