#!/bin/sh
set -eu
if [ ! -f /data/ca.pem ]; then
  openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
    -keyout /data/ca.key -out /data/ca.pem \
    -subj '/CN=Lab Demo CA01/O=Purdue OT Lab' >/dev/null 2>&1
  chmod 600 /data/ca.key
fi
cd /data
exec python -m http.server 8080 --bind 0.0.0.0
