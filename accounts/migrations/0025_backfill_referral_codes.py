from django.db import migrations


def backfill_referral_codes(apps, schema_editor):
    """Har bir foydalanuvchida id_number va referral_code bo'lishini ta'minlaydi.
    Eski (kodsiz) foydalanuvchilar promokodini kiritganda 'topilmadi' bo'lmasligi uchun."""
    import random
    User = apps.get_model('accounts', 'User')

    used_ids = set(
        User.objects.exclude(id_number__isnull=True).values_list('id_number', flat=True)
    )

    for user in User.objects.filter(id_number__isnull=True):
        while True:
            rid = random.randint(100000, 999999)
            if rid not in used_ids:
                used_ids.add(rid)
                break
        user.id_number = rid
        user.save(update_fields=['id_number'])

    for user in User.objects.filter(referral_code__isnull=True) | User.objects.filter(referral_code=''):
        if user.id_number:
            user.referral_code = f'GOLD{user.id_number}'
            user.save(update_fields=['referral_code'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0024_taxipark_telegram_chat_id'),
    ]

    operations = [
        migrations.RunPython(backfill_referral_codes, noop),
    ]
