FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates tzdata && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

# Criar diretório para dados persistentes
RUN mkdir -p /app/data

# Default envs (override in EasyPanel)
ENV PORT=8000 \
    TIMEZONE=America/Sao_Paulo \
    DB_PATH=/app/data/advocacia.db

EXPOSE 8000

# Gunicorn WSGI server
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:8000", "app:application"]



