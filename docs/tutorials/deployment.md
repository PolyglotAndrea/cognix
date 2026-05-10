# Deploy to Production

This guide covers deploying Cognix to a production environment.

## Prerequisites

- A server with Python 3.11+
- PostgreSQL database
- Domain name (optional but recommended)
- SSL certificate (for HTTPS)

## Step 1: Set Up the Database

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE cognix;
CREATE USER cognix WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE cognix TO cognix;
\q
```

## Step 2: Install Cognix

```bash
# Clone the repository
git clone https://github.com/PolyglotAndrea/cognix.git
cd cognix

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .
```

## Step 3: Configure Environment

Create `.env`:

```bash
# Core
COGNIX_DEBUG=false
COGNIX_DEFAULT_MODEL=gpt-4o
COGNIX_LLM_API_KEY=sk-...

# Database
COGNIX_DATABASE__URL=postgresql+asyncpg://cognix:secure-password@localhost:5432/cognix

# Auth
COGNIX_AUTH__SECRET_KEY=$(openssl rand -hex 32)
COGNIX_AUTH__FRONTEND_URL=https://your-domain.com

# Server
COGNIX_SERVER__HOST=0.0.0.0
COGNIX_SERVER__PORT=8000

# Billing (optional)
COGNIX_BILLING__STRIPE_SECRET_KEY=sk_...
COGNIX_BILLING__STRIPE_WEBHOOK_SECRET=whsec_...
```

## Step 4: Run Database Migrations

```bash
alembic upgrade head
```

## Step 5: Build the Frontend

```bash
cd web
npm install
npm run build
```

The built files will be in `web/dist/`. Serve them with nginx or a CDN.

## Step 6: Set Up Process Management

### Systemd Service

Create `/etc/systemd/system/cognix.service`:

```ini
[Unit]
Description=Cognix API Server
After=network.target postgresql.service

[Service]
Type=simple
User=cognix
WorkingDirectory=/opt/cognix
Environment=PATH=/opt/cognix/.venv/bin
ExecStart=/opt/cognix/.venv/bin/cognix server start --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable cognix
sudo systemctl start cognix
```

### Supervisor (Alternative)

```ini
[program:cognix]
command=/opt/cognix/.venv/bin/cognix server start --port 8000
directory=/opt/cognix
user=cognix
autostart=true
autorestart=true
```

## Step 7: Set Up Nginx

Create `/etc/nginx/sites-available/cognix`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Frontend
    location / {
        root /opt/cognix/web/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Auth
    location /auth/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Billing
    location /billing/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # RPC
    location /rpc {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/cognix /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Step 8: SSL Certificate

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Step 9: Configure Stripe Webhooks

In your Stripe dashboard, add a webhook endpoint:

```
https://your-domain.com/billing/webhook
```

Select events:
- `checkout.session.completed`
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.deleted`
- `customer.subscription.updated`

## Monitoring

### Health Check

```bash
curl https://your-domain.com/health
# {"status": "ok", "version": "0.1.0"}
```

### Logs

```bash
# Systemd
sudo journalctl -u cognix -f

# Supervisor
sudo tail -f /var/log/cognix/stdout.log
```

### Database Backup

```bash
# Automated daily backup
pg_dump -U cognix cognix | gzip > /backups/cognix-$(date +%Y%m%d).sql.gz
```

## Security Checklist

- [ ] `COGNIX_DEBUG=false` in production
- [ ] Strong `COGNIX_AUTH__SECRET_KEY` (64+ random characters)
- [ ] PostgreSQL with strong password
- [ ] HTTPS enabled
- [ ] Firewall configured (only ports 80, 443)
- [ ] Regular database backups
- [ ] Stripe webhook secret configured
- [ ] Rate limiting on auth endpoints (via nginx)
