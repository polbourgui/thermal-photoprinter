FROM python:3.11-slim

# libusb is required by python-escpos for USB printer access
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Config directory is mounted as a volume so settings persist across restarts
RUN mkdir -p config

ENV PYTHONPATH=/app/src
ENV CONFIG_PATH=/app/config/settings.json

EXPOSE 8080

CMD ["python", "src/main.py"]
