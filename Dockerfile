FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed by reportlab, lxml, pillow
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create data directories
RUN mkdir -p /app/data/reports

EXPOSE 8080

CMD ["python", "dashboard/app.py"]
