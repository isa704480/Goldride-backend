from django.db import migrations


def ensure_admin(apps, schema_editor):
    """Admin superuser mavjud va 'admin123' paroli bilan ishlashini ta'minlaydi.
    (DB tozalash paytida admin ta'sirlangan bo'lsa — tiklaydi.)"""
    from django.contrib.auth.hashers import make_password
    User = apps.get_model('accounts', 'User')

    admin = User.objects.filter(phone='admin').first() or User.objects.filter(username='admin').first()
    if admin is None:
        # 'admin' foydalanuvchisi topilmadi — yaratamiz
        admin = User(phone='admin', username='admin')
    admin.username = 'admin'
    admin.phone = 'admin'
    admin.is_staff = True
    admin.is_superuser = True
    admin.is_active = True
    admin.is_verified = True
    admin.is_blocked = False
    admin.password = make_password('admin123')
    admin.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_user_block_reason_user_blocked_at'),
    ]

    operations = [
        migrations.RunPython(ensure_admin, noop),
    ]
