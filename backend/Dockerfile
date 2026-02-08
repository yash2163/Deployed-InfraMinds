# backend/Dockerfile
FROM python:3.10-slim

# Install system dependencies and Terraform CLI
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    software-properties-common \
    unzip \
    && curl -fsSL https://apt.releases.hashicorp.com/gpg | apt-key add - \
    && apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    && apt-get update && apt-get install -y terraform \
    && apt-get clean

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# Render uses the PORT environment variable
ENV PORT=8000
EXPOSE 8000

# Start FastAPI with Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]