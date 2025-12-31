# Deploy instructions — Gunicorn + systemd + Nginx

These are example steps to deploy DocuExpress on a Debian/Ubuntu server.

1) Copy service/socket files

  - Copy `deploy/gunicorn.service` to `/etc/systemd/system/gunicorn-docuexpress.service`
  - Copy `deploy/gunicorn.socket` to `/etc/systemd/system/gunicorn-docuexpress.socket`

2) Adjust service settings

  - Edit `User=` and `Group=` in the service file to the user that owns the project (e.g. `vladtrix`).
  - Ensure `WorkingDirectory` points to the project root and `Environment=PATH` points to the venv `bin`.

3) Reload systemd, enable socket and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn-docuexpress.socket
sudo systemctl status gunicorn-docuexpress.socket
sudo systemctl start gunicorn-docuexpress.service
sudo journalctl -u gunicorn-docuexpress.service -f
```

Note: enabling the socket will make systemd listen on the socket and spawn the service when connections arrive.

4) Nginx configuration

  - Copy `deploy/nginx_docuexpress.conf` to `/etc/nginx/sites-available/docuexpress` and create a symlink to `sites-enabled`:

```bash
sudo cp deploy/nginx_docuexpress.conf /etc/nginx/sites-available/docuexpress
sudo ln -s /etc/nginx/sites-available/docuexpress /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

5) Firewall and SSL

  - Allow HTTP/HTTPS in firewall (ufw): `sudo ufw allow 'Nginx Full'`.
  - Use Certbot to obtain certificates and update the nginx config to listen on 443.

6) Logs and troubleshooting

  - Gunicorn logs via systemd: `sudo journalctl -u gunicorn-docuexpress.service`.
  - Nginx logs: `/var/log/nginx/access.log` and `error.log`.

7) Extras

  - Consider running Gunicorn with more workers for higher concurrency (match to CPU cores): `--workers 3`.
  - Use a process monitoring tool like `systemd` (already used here) or `supervisord` if preferred.
