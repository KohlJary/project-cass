# Cass Vessel - Deployment Guide

Guide for deploying the Cass Vessel backend to a production environment.

## Prerequisites

- Python 3.10+
- nginx (for reverse proxy)
- SSL certificate (Let's Encrypt recommended)
- Systemd (for service management)

## Environment Setup

### 1. Clone and Install

```bash
cd /opt
git clone <repo-url> cass-vessel
cd cass-vessel/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy and edit the environment file:

```bash
cp .env.example .env
nano .env
```

**Required settings:**
```bash
# Claude API - get from console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-...

# JWT Secret - generate with: openssl rand -hex 32
JWT_SECRET_KEY=<your-secret-key>

# Disable localhost bypass in production
ALLOW_LOCALHOST_BYPASS=false
```

**Optional settings:**
```bash
# Data directory (default: ./data)
DATA_DIR=/var/lib/cass-vessel/data

# Debug mode (default: false)
DEBUG=false

# CORS origins (comma-separated)
ALLOWED_ORIGINS=https://your-domain.com

# OpenAI support
OPENAI_ENABLED=true
OPENAI_API_KEY=sk-proj-...

# Local LLM (Ollama)
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. Create Data Directory

```bash
sudo mkdir -p /var/lib/cass-vessel/data
sudo chown -R cass:cass /var/lib/cass-vessel
```

## Systemd Service

### 1. Create Service File

Create `/etc/systemd/system/cass-vessel.service`:

```ini
[Unit]
Description=Cass Vessel Backend
After=network.target

[Service]
Type=simple
User=cass
Group=cass
WorkingDirectory=/opt/cass-vessel/backend
Environment=PATH=/opt/cass-vessel/backend/venv/bin
ExecStart=/opt/cass-vessel/backend/venv/bin/python main_sdk.py
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/cass-vessel

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable cass-vessel
sudo systemctl start cass-vessel
sudo systemctl status cass-vessel
```

### 3. View Logs

```bash
journalctl -u cass-vessel -f
```

## Nginx Reverse Proxy

### 1. Install nginx

```bash
sudo apt install nginx
```

### 2. Configure Site

Copy the template and customize:

```bash
sudo cp /opt/cass-vessel/backend/nginx.conf.template /etc/nginx/sites-available/cass-vessel
sudo nano /etc/nginx/sites-available/cass-vessel
```

Replace `YOUR_DOMAIN_HERE` with your actual domain.

### 3. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/cass-vessel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## SSL Certificate (Let's Encrypt)

### 1. Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx
```

### 2. Obtain Certificate

```bash
sudo certbot --nginx -d your-domain.com
```

### 3. Auto-renewal

Certbot automatically sets up renewal. Test with:

```bash
sudo certbot renew --dry-run
```

## Health Checks

The backend exposes a health endpoint:

```bash
curl https://your-domain.com/health
```

Response:
```json
{
  "status": "ok",
  "version": "0.2.0",
  "llm_provider": "anthropic",
  "memory_entries": 1234
}
```

## Monitoring

### Log Files

- Backend: `journalctl -u cass-vessel`
- nginx access: `/var/log/nginx/cass-vessel-access.log`
- nginx errors: `/var/log/nginx/cass-vessel-error.log`

### Key Metrics to Monitor

- Health endpoint response time
- Rate limit 429 responses (indicates abuse or need for limit adjustment)
- Memory entry count growth
- WebSocket connection counts

## Backup

### Data Directory

```bash
# Stop service for consistent backup
sudo systemctl stop cass-vessel

# Backup data
tar -czf cass-vessel-backup-$(date +%Y%m%d).tar.gz /var/lib/cass-vessel/data

# Restart service
sudo systemctl start cass-vessel
```

### Database (ChromaDB)

ChromaDB data is in `DATA_DIR/chroma/`. Include in data directory backup.

## Troubleshooting

### Service Won't Start

1. Check logs: `journalctl -u cass-vessel -n 50`
2. Verify env file: `cat /opt/cass-vessel/backend/.env`
3. Check permissions on data directory
4. Validate API key is set

### 502 Bad Gateway

1. Check if backend is running: `systemctl status cass-vessel`
2. Check backend port: `curl http://localhost:8000/health`
3. Check nginx error logs

### Rate Limiting Issues

Default limits:
- Auth endpoints: 5-30/min per IP
- API endpoints: 30-60/min per user

Adjust in `main_sdk.py` if needed for your use case.

### WebSocket Connection Fails

1. Check nginx WebSocket configuration
2. Verify `/ws` endpoint proxying
3. Check firewall allows WebSocket upgrade

## Security Checklist

- [ ] Changed JWT_SECRET_KEY from default
- [ ] Set ALLOW_LOCALHOST_BYPASS=false
- [ ] Configured ALLOWED_ORIGINS for your domain
- [ ] SSL certificate installed and valid
- [ ] Firewall configured (only 80/443 open)
- [ ] Service running as non-root user
- [ ] Data directory permissions restricted
- [ ] DEBUG=false in production
