# DocuExpress — Running & Deploying

Quick notes to run and deploy the application locally and in production.

Prerequisites
- Python 3.10 (virtualenv recommended)
- Create and activate virtualenv at project root: `python3 -m venv .venv` and `source .venv/bin/activate`
- Install dependencies (see `requirements.txt`)

Local development

- Run as package (recommended):
```
PYTHONPATH="/home/vladtrix/DOCUEXPRESS PAGINA" RATELIMIT_ENABLED=False ./.venv/bin/python3 -m ARCHIVOS
```

- Or use the existing runner:
```
PYTHONPATH="/home/vladtrix/DOCUEXPRESS PAGINA" RATELIMIT_ENABLED=False ./.venv/bin/python3 run_local.py
```

- Health check:
```
curl -sS http://127.0.0.1:8083/health
```

Notes
- Do NOT run `python ARCHIVOS/app.py` directly — the app uses package-style absolute imports and must be executed as a package or via the runner.
- Use `RATELIMIT_ENABLED=False` locally if you don't have Redis available.

Production (Gunicorn + systemd)

- Example gunicorn command (run from project root):
```
PYTHONPATH="/home/vladtrix/DOCUEXPRESS PAGINA" ./.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 "ARCHIVOS.app:create_app()"
```

- A sample systemd unit is provided in `deploy/gunicorn.service`. Edit `User`, `Group`, `WorkingDirectory` and `Environment` entries to match your server.

PythonAnywhere
- Point the WSGI file to `wsgi.py` in the repository, ensure `PYTHONPATH` includes the project parent folder, and install dependencies into PythonAnywhere's virtualenv.

Further
- `run_wsgi_test.py` is included to quickly verify `wsgi.application` with wsgiref.
- If you want, I can also create a Dockerfile or push these commits to a remote repo if you provide the URL.

Contact
- Ask me to: create Dockerfile / push to remote / adjust systemd unit with your user/paths.
