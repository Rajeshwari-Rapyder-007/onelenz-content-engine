FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/services/email-connector/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY backend/shared ./shared

# Copy email-connector code
COPY backend/services/email-connector ./email-connector

# Set PYTHONPATH so 'shared' and 'app' are importable
ENV PYTHONPATH="/app:/app/email-connector"

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
