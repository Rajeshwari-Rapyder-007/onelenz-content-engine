FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/services/auth-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY backend/shared ./shared

# Copy auth-service code
COPY backend/services/auth-service ./auth-service

# Set PYTHONPATH so 'shared' and 'app' are importable
ENV PYTHONPATH="/app:/app/auth-service"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
