FROM python:3.11-slim

# Install PostgreSQL client and WeasyPrint dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libgirepository1.0-dev \
    gir1.2-gobject-2.0 \
    gir1.2-pango-1.0 \
    gir1.2-gtk-3.0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=True
ENV ALLOWED_HOSTS=localhost,127.0.0.1

# Set work directory
WORKDIR /app

# Install dependencies with fixes
COPY requirements.txt .
RUN pip install --upgrade pip wheel setuptools
# Install WeasyPrint separately to avoid dependency issues
RUN pip install weasyprint==53.0
# Install remaining requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy project and entrypoint script
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]