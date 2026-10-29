FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
COPY start.sh /usr/local/bin/start-ca
RUN chmod 755 /usr/local/bin/start-ca
CMD ["/usr/local/bin/start-ca"]
