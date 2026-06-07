FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies (e.g., for NVIDIA support or networking)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies directly
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Run the app
CMD ["python", "run.py"]