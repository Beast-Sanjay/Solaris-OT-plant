#!/bin/sh
set -eu
: "${JUMP_PASSWORD:?missing JUMP_PASSWORD}"
printf 'labops:%s\n' "$JUMP_PASSWORD" | chpasswd
printf 'PasswordAuthentication yes\nPermitRootLogin no\nAllowUsers labops\nX11Forwarding no\nAllowTcpForwarding no\nPermitTunnel no\n' >/etc/ssh/sshd_config.d/lab.conf
ssh-keygen -A
exec /usr/sbin/sshd -D -e
