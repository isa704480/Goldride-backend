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

echo "Starting Telegram Bot in background..."
python manage.py run_bot &

echo "Starting Daphne server on port ${PORT:-8000}..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
