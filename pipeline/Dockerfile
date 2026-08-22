FROM python:3.12-slim

# LibreOffice converts legacy binary .doc -> .docx; Noto fonts render Arabic.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer fonts-noto fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SOFFICE_PATH=/usr/bin/soffice \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

# CLI container: `docker run <img> --input /data/in --output /data/out ...`
ENTRYPOINT ["python", "-m", "anonymizer"]
CMD ["--help"]
