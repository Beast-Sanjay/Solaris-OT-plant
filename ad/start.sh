#!/bin/sh
set -eu
: "${AD_REALM:?missing AD_REALM}" "${AD_NETBIOS:?missing AD_NETBIOS}" "${AD_ADMIN_PASSWORD:?missing AD_ADMIN_PASSWORD}" "${AD_IP:?missing AD_IP}"
# Persist Samba's database and generated smb.conf across restarts.
if [ ! -f /var/lib/samba/private/sam.ldb ]; then
  echo "[ad] Provisioning isolated $AD_REALM domain, first boot"
  rm -f /etc/samba/smb.conf
  samba-tool domain provision \
    --use-rfc2307 \
    --realm="$AD_REALM" \
    --domain="$AD_NETBIOS" \
    --server-role=dc \
    --dns-backend=SAMBA_INTERNAL \
    --adminpass="$AD_ADMIN_PASSWORD" \
    --option="dns forwarder = 127.0.0.11" \
    --option="interfaces = lo eth0" \
    --option="bind interfaces only = yes"
  if [ -n "${AD_USER:-}" ] && [ -n "${AD_USER_PASSWORD:-}" ]; then
    samba-tool user create "$AD_USER" "$AD_USER_PASSWORD" --given-name=Lab --surname=User
  fi
fi
if [ -f /var/lib/samba/private/krb5.conf ]; then
  cp -f /var/lib/samba/private/krb5.conf /etc/krb5.conf
fi
chmod 600 /etc/samba/smb.conf || true
samba-tool domain level show || true
printf '[ad] Starting samba DC: %s (%s)\n' "$AD_REALM" "$AD_IP"
exec samba -i -M single
