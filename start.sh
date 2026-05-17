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

echo "Auto-approving and funding all registered drivers..."
python manage.py shell -c "
from accounts.models import Driver, Wallet
for d in Driver.objects.all():
    d.status = 'approved'
    d.save()
    d.user.is_verified = True
    d.user.save()
    w, _ = Wallet.objects.get_or_create(user=d.user)
    if w.balance < 20000:
        w.deposit(50000, 'Avtomatik sinov bonusi')
        print(f'Approved and funded driver: {d.user.phone}')
" 2>&1 || echo "Driver auto-approval check skipped"


echo "Starting Telegram Bot in background..."
python manage.py run_bot &

echo "Starting Daphne server on port ${PORT:-8000}..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
