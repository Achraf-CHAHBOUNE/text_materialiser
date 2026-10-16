# The platform's API, and with another command its worker and its operations tools.
# Ingest-only: no LibreOffice, no anonymization engine -- it serves anonymized content.
FROM python:3.12.14-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Never root inside the container: a flaw in the API gives no more than this user.
RUN useradd --system --uid 10001 --home /app app && chown -R app /app
USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# --proxy-headers: behind Caddy, the reader's address comes from X-Forwarded-For.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${API_WORKERS:-1}"]
