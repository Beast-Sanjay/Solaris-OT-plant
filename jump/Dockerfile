FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server curl iproute2 dnsutils ldap-utils \
    && mkdir -p /run/sshd && useradd -m -s /bin/bash labops \
    && rm -rf /var/lib/apt/lists/*
COPY start.sh /usr/local/bin/start-jump
RUN chmod 755 /usr/local/bin/start-jump
EXPOSE 22
CMD ["/usr/local/bin/start-jump"]
