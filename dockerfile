FROM python:3.14-slim

RUN apt-get update && apt-get install -y gosu && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1000 appgroup && \
    adduser --system --uid 1000 --ingroup appgroup --home /home/appuser appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    mkdir -p /config && \
    chown -R appuser:appgroup /config /app

EXPOSE 6580

ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:6580", "--access-logfile", "-", "--error-logfile", "-", "app:app"]