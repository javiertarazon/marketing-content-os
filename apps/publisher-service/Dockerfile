FROM python:3.12-slim

WORKDIR /app
COPY apps/publisher-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/publisher-service/main.py .
COPY apps/publisher-service/adapters /app/adapters
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
