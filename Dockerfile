FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py .

# Make app.py executable
RUN chmod +x app.py

# Run the application
ENTRYPOINT ["python3", "app.py"]
CMD []

