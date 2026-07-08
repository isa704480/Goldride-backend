from django.db import migrations


def flush_test_data(apps, schema_editor):
    """BIR MARTALIK: barcha safarlar, so'rovlar va staff BO'LMAGAN foydalanuvchilarni
    o'chiradi (test ma'lumotlarini tozalash). Staff/superuser (admin), taksi parklar
    va narx sozlamalari SAQLANADI. Hech qachon deploy'ni yiqitmaydi (try/except)."""
    try:
        User = apps.get_model('accounts', 'User')
        Ride = apps.get_model('rides', 'Ride')
        RideRequest = apps.get_model('rides', 'RideRequest')

        # Avval safar-bog'liq yozuvlar (CASCADE bilan RidePassenger/chat/rating ham ketadi)
        RideRequest.objects.all().delete()
        Ride.objects.all().delete()

        # Staff/superuser bo'lmagan barcha foydalanuvchilar
        # (haydovchi profili, hamyon, tranzaksiyalar CASCADE bilan o'chadi)
        User.objects.filter(is_staff=False, is_superuser=False).delete()
    except Exception:
        pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0027_ensure_admin'),
        ('rides', '0012_add_payment_method'),
    ]

    operations = [
        migrations.RunPython(flush_test_data, noop),
    ]
