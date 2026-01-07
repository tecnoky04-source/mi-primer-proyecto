#!/usr/bin/env bash
# Despliegue automático (guía) para una VM Ubuntu en Oracle Cloud (Always Free)
# USO:
#   sudo REPO_URL="git@github.com:usuario/mi-repo.git" TARGET_DIR="/opt/docuexpress" ./deploy/oracle_deploy.sh
# Opciones (variables de entorno): REPO_URL, BRANCH (default main), TARGET_DIR, DOMAIN (opcional para certbot)

set -euo pipefail

REPO_URL=${REPO_URL:-}
BRANCH=${BRANCH:-main}
TARGET_DIR=${TARGET_DIR:-/opt/docuexpress}
DOMAIN=${DOMAIN:-}

if [ -z "$REPO_URL" ]; then
  echo "ERROR: debes exportar REPO_URL antes de ejecutar el script. Ej:"
  echo "  sudo REPO_URL=\"git@github.com:usuario/mi-repo.git\" ./deploy/oracle_deploy.sh"
  exit 1
fi

echo "Instalando dependencias del sistema..."
apt-get update
apt-get install -y git python3 python3-venv python3-pip nginx redis-server build-essential curl
apt-get install -y certbot python3-certbot-nginx || true

echo "Creando usuario y directorio de despliegue si es necesario..."
TARGET_PARENT=$(dirname "$TARGET_DIR")
mkdir -p "$TARGET_PARENT"
chown root:root "$TARGET_PARENT" || true

if [ ! -d "$TARGET_DIR" ]; then
  echo "Clonando repo ($REPO_URL) en $TARGET_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
else
  echo "Directorio $TARGET_DIR ya existe — actualizando código"
  git -C "$TARGET_DIR" fetch --all
  git -C "$TARGET_DIR" checkout "$BRANCH"
  git -C "$TARGET_DIR" pull origin "$BRANCH"
fi

echo "Creando virtualenv e instalando dependencias Python..."
python3 -m venv "$TARGET_DIR/.venv"
source "$TARGET_DIR/.venv/bin/activate"
pip install --upgrade pip
if [ -f "$TARGET_DIR/requirements.txt" ]; then
  pip install -r "$TARGET_DIR/requirements.txt"
else
  echo "Advertencia: no encontré requirements.txt en el repo. Instala dependencias manualmente." >&2
fi
deactivate || true

echo "Copiando .env.example a .env (edítalo con las variables reales)..."
if [ -f "$TARGET_DIR/.env.example" ] && [ ! -f "$TARGET_DIR/.env" ]; then
  cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"
  echo "=> Se creó $TARGET_DIR/.env desde .env.example. Edítalo con tus secretos."
fi

SERVICE_FILE=/etc/systemd/system/docuexpress_gunicorn.service
SOCKET_FILE=/etc/systemd/system/docuexpress_gunicorn.socket

echo "Creando systemd socket y service para Gunicorn..."
cat > "$SOCKET_FILE" <<EOF
[Unit]
Description=Gunicorn socket for DocuExpress
ListenStream=/run/gunicorn-docuexpress.sock
SocketUser=www-data
SocketGroup=www-data

[Install]
WantedBy=sockets.target
EOF

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Gunicorn instance to serve DocuExpress
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$TARGET_DIR
ExecStart=/bin/bash -lc 'cd "$TARGET_DIR" && exec "$TARGET_DIR/.venv/bin/gunicorn" --workers 3 --bind unix:/run/gunicorn-docuexpress.sock wsgi:application'
Restart=on-failure
RuntimeDirectory=gunicorn-docuexpress

[Install]
WantedBy=multi-user.target
EOF

echo "Recargando systemd y activando socket..."
systemctl daemon-reload
systemctl enable --now docuexpress_gunicorn.socket

echo "Creando configuración Nginx..."
NGINX_CONF=/etc/nginx/sites-available/docuexpress
cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${DOMAIN:-_};

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/run/gunicorn-docuexpress.sock;
    }

    client_max_body_size 16M;
}
EOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/docuexpress
if [ -f /etc/nginx/sites-enabled/default ]; then rm -f /etc/nginx/sites-enabled/default; fi
nginx -t && systemctl reload nginx

echo "Arrancando servicio Gunicorn (vía socket activation)..."
systemctl enable --now docuexpress_gunicorn.service || true

if [ -n "$DOMAIN" ]; then
  echo "Intentando obtener certificado Let's Encrypt para $DOMAIN (se requiere que DNS apunte a esta IP)..."
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@$DOMAIN || true
fi

echo "Despliegue terminado. Revisa logs si algo falla:"
echo "  sudo journalctl -u docuexpress_gunicorn.service -f"
echo "  sudo tail -n 200 /var/log/nginx/error.log"

exit 0
