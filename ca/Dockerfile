FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY ca_service.py /app/ca_service.py
WORKDIR /app
EXPOSE 8080
CMD ["python", "-u", "/app/ca_service.py"]
