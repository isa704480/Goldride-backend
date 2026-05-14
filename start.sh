#!/bin/bash
set -e

echo "=== GOLDRIDE BACKEND STARTUP ==="
echo "Running migrations..."
python manage.py migrate --no-input 2>&1
echo "Migration complete!"

echo "Creating superuser if needed..."
python manage.py shell -c "
from accounts.models import User
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(username='admin', phone='+998901234567', password='admin123', role='admin')
    print('Superuser created')
else:
    print('Superuser already exists')
" 2>&1 || echo "Superuser check skipped"

echo "Starting Daphne server on port ${PORT:-8000}..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
