FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    samba-ad-dc samba-ad-provision samba-common-bin smbclient krb5-user dnsutils ldap-utils acl attr ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY start.sh /usr/local/bin/start-ad
RUN chmod 755 /usr/local/bin/start-ad
EXPOSE 53/tcp 53/udp 88/tcp 88/udp 135/tcp 139/tcp 389/tcp 389/udp 445/tcp 464/tcp 464/udp 636/tcp 3268/tcp 3269/tcp
ENTRYPOINT ["/usr/local/bin/start-ad"]
