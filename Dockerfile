FROM python:3.12-slim

# The charger connects INBOUND to this port (OCPP over ws). Expose for clarity.
EXPOSE 9000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py ha_entities.py bridge.py ./

# Unbuffered logs so `docker logs` is live.
ENV PYTHONUNBUFFERED=1

CMD ["python", "bridge.py"]
