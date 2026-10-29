FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    krb5-user ldap-utils dnsutils smbclient curl iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*
CMD ["sleep", "infinity"]
