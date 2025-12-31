#!/usr/bin/env bash
set -euo pipefail

# deploy/install.sh
# Copy service/socket and nginx config to system locations and enable them.
# Usage: sudo ./deploy/install.sh -u <user> -g <group> -d <domain>

usage(){
  cat <<EOF
Usage: sudo $0 [-u user] [-g group] [-d domain]

Options:
  -u user    User to run the service as (default: vladtrix)
  -g group   Group to run the service as (default: www-data)
  -d domain  Domain to configure in the nginx server_name (optional)

This script copies:
  - deploy/gunicorn.service -> /etc/systemd/system/gunicorn-docuexpress.service
  - deploy/gunicorn.socket  -> /etc/systemd/system/gunicorn-docuexpress.socket
  - deploy/nginx_docuexpress.conf -> /etc/nginx/sites-available/docuexpress

Edit the files in the repo first if you need custom paths. The script can
replace the default user/group/domain placeholders when provided.
EOF
}

USER_NAME="vladtrix"
GROUP_NAME="www-data"
DOMAIN=""

while getopts ":u:g:d:h" opt; do
  case ${opt} in
    u ) USER_NAME=$OPTARG ;;
    g ) GROUP_NAME=$OPTARG ;;
    d ) DOMAIN=$OPTARG ;;
    h ) usage; exit 0 ;;
    \? ) usage; exit 1 ;;
  esac
done

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run with sudo/root. Re-run with: sudo $0 ..."
  exit 1
fi

ROOT=$(pwd)
echo "Project root: $ROOT"

SRC_SERVICE="$ROOT/deploy/gunicorn.service"
SRC_SOCKET="$ROOT/deploy/gunicorn.socket"
SRC_NGINX="$ROOT/deploy/nginx_docuexpress.conf"

DEST_SERVICE="/etc/systemd/system/gunicorn-docuexpress.service"
DEST_SOCKET="/etc/systemd/system/gunicorn-docuexpress.socket"
DEST_NGINX="/etc/nginx/sites-available/docuexpress"

for f in "$SRC_SERVICE" "$SRC_SOCKET" "$SRC_NGINX"; do
  if [ ! -f "$f" ]; then
    echo "Missing file: $f"; exit 1
  fi
done

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

echo "Preparing files with user=$USER_NAME group=$GROUP_NAME domain=$DOMAIN"

# service
sed "s/^User=.*/User=$USER_NAME/; s/^Group=.*/Group=$GROUP_NAME/" "$SRC_SERVICE" > "$tmpdir/gunicorn.service"

# socket (no changes normally, but ensure SocketUser/Group if present)
sed "s/^SocketUser=.*/SocketUser=$USER_NAME/; s/^SocketGroup=.*/SocketGroup=$GROUP_NAME/" "$SRC_SOCKET" > "$tmpdir/gunicorn.socket"

# nginx
if [ -n "$DOMAIN" ]; then
  sed "s/server_name .*/server_name $DOMAIN;\/\/ replaced by deploy script/" "$SRC_NGINX" > "$tmpdir/nginx.conf"
else
  cp "$SRC_NGINX" "$tmpdir/nginx.conf"
fi

echo "Copying files to system locations (requires root)"
cp "$tmpdir/gunicorn.service" "$DEST_SERVICE"
cp "$tmpdir/gunicorn.socket" "$DEST_SOCKET"
cp "$tmpdir/nginx.conf" "$DEST_NGINX"

echo "Setting permissions"
chmod 644 "$DEST_SERVICE" "$DEST_SOCKET" "$DEST_NGINX"

echo "Reloading systemd and enabling socket/service"
systemctl daemon-reload
systemctl enable --now gunicorn-docuexpress.socket
systemctl restart gunicorn-docuexpress.service || true

echo "Testing nginx configuration"
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || echo "nginx test/ reload failed — check /var/log/nginx/error.log"
else
  echo "nginx not found on this host; please copy $DEST_NGINX to a host running nginx and enable it."
fi

echo "Done. Check status with: systemctl status gunicorn-docuexpress.service"
echo "Journal logs: journalctl -u gunicorn-docuexpress.service -f"
