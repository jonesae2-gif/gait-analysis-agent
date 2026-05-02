# Minimal container for the GaitMind demo.
FROM python:3.11-slim

WORKDIR /app

# System deps kept lean — pandas/numpy provide their own wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first so the layer is cached.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy the rest of the project.
COPY backend  /app/backend
COPY frontend /app/frontend

WORKDIR /app/backend
EXPOSE 8000

# Use uvicorn directly so we get sensible logging in containers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
