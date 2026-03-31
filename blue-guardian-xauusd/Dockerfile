FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for scientific stack and build tools
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
		build-essential \
		gcc \
		git \
		libpq-dev \
		libffi-dev \
		libssl-dev \
		curl \
		&& rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Set environment variables for unbuffered output and timezone
ENV PYTHONUNBUFFERED=1 \
	TZ=UTC

# Entrypoint for the Blue Guardian system (runs the morning routine script)
CMD ["python", "scripts/morning_run.py"]
