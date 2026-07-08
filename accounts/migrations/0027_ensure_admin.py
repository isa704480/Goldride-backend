from django.db import migrations


def ensure_admin(apps, schema_editor):
    """Admin superuser parolini 'admin123' ga tiklaydi (agar mavjud bo'lsa).
    HECH QACHON deploy'ni yiqitmaydi — barcha xatolar yutiladi."""
    try:
        from django.contrib.auth.hashers import make_password
        User = apps.get_model('accounts', 'User')
        admin = User.objects.filter(phone='admin').first() or User.objects.filter(username='admin').first()
        if admin is None:
            return
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        admin.password = make_password('admin123')
        # Faqat kerakli maydonlar — phone/username'ga tegmaymiz (unique to'qnashuv bo'lmasin)
        admin.save(update_fields=['is_staff', 'is_superuser', 'is_active', 'password'])
    except Exception:
        pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_user_block_reason_user_blocked_at'),
    ]

    operations = [
        migrations.RunPython(ensure_admin, noop),
    ]
