FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY metrics_exporter.py .

# Expose metrics port
EXPOSE 8001

# Run the metrics exporter
CMD ["python", "metrics_exporter.py"]