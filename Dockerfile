FROM python:3.11-slim

# Install PostgreSQL client
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=True
ENV ALLOWED_HOSTS=localhost,127.0.0.1
ENV DJANGO_SETTINGS_MODULE=mywebsite.settings

# Set work directory
WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements files
COPY requirements.txt s3_requirements.txt ./

# Install S3 requirements first
RUN pip install --no-cache-dir -r s3_requirements.txt

# Install other dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]