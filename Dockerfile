FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY prompts/ ./prompts/

EXPOSE 8000

# Por padrão sobe a API. O worker do Celery sobe via docker-compose (command).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
