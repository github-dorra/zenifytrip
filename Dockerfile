FROM python:3.13-slim

WORKDIR /app

# Dépendances système (compilateurs pour packages C-extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code applicatif
COPY app/ ./app/
COPY .env* ./

# Répertoire de cache JSON (hôtels, vols, météo — volume Docker en prod)
RUN mkdir -p app/.cache

# Utilisateur non-root pour la sécurité
RUN useradd -m -u 1000 zenify && chown -R zenify:zenify /app
USER zenify

EXPOSE 8000

# 2 workers Uvicorn — adapté à 4 vCPU Hetzner CX32
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-keep-alive", "120"]
