FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py private_channel.py ./
COPY static ./static
COPY templates ./templates
RUN mkdir -p /data/files && useradd --uid 10001 --home-dir /nonexistent --no-create-home hamoki && chown -R hamoki:hamoki /data
USER hamoki
ENV DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
