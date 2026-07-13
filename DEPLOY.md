# PRLMAD Linux deployment

This guide assumes an Ubuntu 24.04 server and deploys PRLMAD with:

- Python virtual environment
- systemd process supervision
- Nginx reverse proxy
- SQLite files stored under `/opt/prlmad/data`

If your server is Windows, use the same project `.venv` idea, but replace systemd/Nginx with NSSM/IIS or a Windows service wrapper.

## 1. Prepare the server

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip
sudo useradd --system --create-home --shell /usr/sbin/nologin prlmad
```

## 2. Put the code on the server

Recommended path:

```bash
sudo git clone https://github.com/csyxcsyx/PRLMAD.git /opt/prlmad
sudo chown -R prlmad:prlmad /opt/prlmad
```

If you need to deploy your local modified version instead of GitHub `master`, upload the project with `scp` or `rsync`, excluding `.venv`, `.git`, and `__pycache__`.

## 3. Create the virtual environment

```bash
cd /opt/prlmad
sudo -u prlmad python3 -m venv .venv
sudo -u prlmad .venv/bin/python -m pip install --upgrade pip
sudo -u prlmad .venv/bin/python -m pip install -r requirements.txt
```

## 4. Configure environment variables

```bash
cd /opt/prlmad
sudo -u prlmad cp .env.example .env
sudo nano .env
```

Set at least:

```text
SPARK_API_KEY=Bearer your-api-password
SPARK_BASE_URL=https://spark-api-open.xf-yun.com/agent/v1/chat/completions
SPARK_MODEL=spark-x
SPARK_USER_ID=prlmad-server
SPARK_ENABLE_WEB_SEARCH=false
SPARK_TRUST_ENV_PROXY=false
PRLMAD_OFFLINE_FALLBACK=false
PRLMAD_DATA_DIR=data
PRLMAD_DB_PATH=data/knowledge.sqlite3
PRLMAD_SESSIONS_DB_PATH=data/sessions.sqlite3
PRLMAD_KNOWLEDGE_DIR=knowledge
PRLMAD_OCR_MODE=auto
PRLMAD_OCR_DPI=150
```

Create writable runtime folders:

```bash
sudo -u prlmad mkdir -p /opt/prlmad/data /opt/prlmad/knowledge
```

## 5. Upload knowledge files and existing SQLite data

If you already trained the knowledge base locally, upload:

- `data/knowledge.sqlite3`
- optional `data/sessions.sqlite3`
- `knowledge/` source documents, if you want to retrain on the server

Example from your Windows machine in PowerShell:

```powershell
scp D:\lizhengyu\Desktop\PRLMAD\data\knowledge.sqlite3 user@SERVER_IP:/tmp/knowledge.sqlite3
scp -r D:\lizhengyu\Desktop\PRLMAD\knowledge user@SERVER_IP:/tmp/prlmad-knowledge
```

Then on the server:

```bash
sudo mv /tmp/knowledge.sqlite3 /opt/prlmad/data/knowledge.sqlite3
sudo rm -rf /opt/prlmad/knowledge
sudo mv /tmp/prlmad-knowledge /opt/prlmad/knowledge
sudo chown -R prlmad:prlmad /opt/prlmad/data /opt/prlmad/knowledge
```

Or retrain on the server:

```bash
cd /opt/prlmad
sudo -u prlmad .venv/bin/python -B run.py train --course 操作系统 --ocr-mode auto
```

## 6. Smoke test before systemd

```bash
cd /opt/prlmad
sudo -u prlmad .venv/bin/python -B -c "from server.main import app; print(app.title)"
sudo -u prlmad .venv/bin/python -B run.py check-spark --timeout 30
sudo -u prlmad .venv/bin/python -B run.py serve --host 127.0.0.1 --port 8000 --no-reload
```

In another SSH session:

```bash
curl http://127.0.0.1:8000/api/health
```

Stop the manual server with `Ctrl+C`.

## 7. Install the systemd service

Copy the service template:

```bash
sudo cp /opt/prlmad/deploy/prlmad.service /etc/systemd/system/prlmad.service
sudo systemctl daemon-reload
sudo systemctl enable --now prlmad
sudo systemctl status prlmad
```

Check logs:

```bash
journalctl -u prlmad -f
```

## 8. Configure Nginx

Edit `deploy/nginx-prlmad.conf` and replace `example.com` with your domain or server IP.

```bash
sudo cp /opt/prlmad/deploy/nginx-prlmad.conf /etc/nginx/sites-available/prlmad
sudo ln -s /etc/nginx/sites-available/prlmad /etc/nginx/sites-enabled/prlmad
sudo nginx -t
sudo systemctl reload nginx
```

Open the firewall if needed:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Visit:

```text
http://your-domain-or-server-ip/
```

## 9. Common operations

Restart after code or `.env` changes:

```bash
sudo systemctl restart prlmad
```

Update code from GitHub:

```bash
cd /opt/prlmad
sudo -u prlmad git pull
sudo -u prlmad .venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart prlmad
```

Check service health:

```bash
curl http://127.0.0.1:8000/api/health
systemctl status prlmad
journalctl -u prlmad -n 100 --no-pager
```

## 10. HTTPS

After DNS points to the server, install Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
```

Certbot will update Nginx and configure certificate renewal.
