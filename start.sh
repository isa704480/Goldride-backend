#!/bin/bash
set -e

echo "=== GOLDRIDE BACKEND STARTUP ==="

echo "Running migrations..."
python manage.py migrate --no-input 2>&1
echo "Migration complete!"

echo "Creating superuser if needed..."
python manage.py shell -c "
from accounts.models import User
import os
admin_phone = os.environ.get('ADMIN_PHONE', '+998901234567')
admin_password = os.environ.get('ADMIN_PASSWORD')
if not admin_password:
    print('WARNING: ADMIN_PASSWORD env var not set — superuser not created')
elif not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
        username='admin',
        phone=admin_phone,
        password=admin_password,
        role='admin'
    )
    print(f'Superuser created: {admin_phone}')
else:
    print('Superuser already exists')
" 2>&1 || echo "Superuser check skipped"

echo "Registering Telegram webhook (polling o'rniga)..."
python manage.py shell -c "
import requests, os
from django.conf import settings

token = settings.TELEGRAM_BOT_TOKEN
base_url = settings.TELEGRAM_WEBHOOK_BASE_URL or os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if not base_url.startswith('http'):
    base_url = 'https://' + base_url if base_url else ''

if token and base_url:
    webhook_url = base_url.rstrip('/') + '/api/accounts/telegram/webhook/'
    r = requests.post(
        f'https://api.telegram.org/bot{token}/setWebhook',
        json={'url': webhook_url, 'allowed_updates': ['message']},
        timeout=10
    )
    resp = r.json()
    if resp.get('ok'):
        print(f'Webhook royhattan otdi: {webhook_url}')
    else:
        print(f'Webhook xatosi: {resp}')
else:
    print('TELEGRAM_BOT_TOKEN yoki TELEGRAM_WEBHOOK_BASE_URL yoq — webhook otkizildi')
" 2>&1 || echo "Webhook setup skipped"

echo "Starting Daphne server on port ${PORT:-8000}..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
