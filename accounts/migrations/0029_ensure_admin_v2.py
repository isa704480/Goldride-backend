from django.db import migrations


def ensure_admin(apps, schema_editor):
    """Admin superuser mavjudligini ta'minlaydi (o'chirilgan bo'lsa qayta yaratadi).
    HECH QACHON deploy'ni yiqitmaydi — har bir DB amali alohida savepoint'da,
    xatolar yutiladi (atomic=False + ichki transaction.atomic)."""
    from django.db import transaction
    try:
        from django.contrib.auth.hashers import make_password
        User = apps.get_model('accounts', 'User')

        admin = User.objects.filter(username='admin').first() or User.objects.filter(phone='admin').first()
        with transaction.atomic():
            if admin is None:
                admin = User(username='admin', phone='admin', first_name='Admin', last_name='', email='', role='passenger', language='uz')
            admin.username = 'admin'
            admin.phone = 'admin'
            admin.is_staff = True
            admin.is_superuser = True
            admin.is_active = True
            admin.is_verified = True
            admin.is_blocked = False
            admin.password = make_password('admin123')
            admin.save()
    except Exception:
        pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False  # save xatosi butun migratsiyani yiqitmasin

    dependencies = [
        ('accounts', '0028_flush_test_data'),
    ]

    operations = [
        migrations.RunPython(ensure_admin, noop),
    ]
