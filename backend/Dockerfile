FROM python:3.10-slim

# Install system dependencies and Terraform manually
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && curl -tfSL https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip -o terraform.zip \
    && unzip terraform.zip \
    && mv terraform /usr/local/bin/ \
    && rm terraform.zip \
    && apt-get purge -y --auto-remove unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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