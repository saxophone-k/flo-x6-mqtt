FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY flo_client/ ./flo_client/
COPY main.py .

# Créer le dossier persistant pour les tokens
RUN mkdir -p /app/data

# Lancer le daemon
CMD ["python3", "-u", "main.py"]
