# Haydovchi maqsad tariflarini belgilash (REKLAMA QOG'OZSIZ):
#   35 buyurtma  → 100.000 so'm + 10 zakas + keyingi 3 kun -2% komissiya
#   55 buyurtma  → 190.000 so'm + 10 zakas + keyingi 3 kun -2% komissiya
#   80 buyurtma  → 280.000 so'm + 10 zakas + keyingi 3 kun -2% komissiya
#   100 buyurtma → 350.000 so'm + 10 zakas + keyingi 3 kun -2% komissiya

from django.db import migrations

GOAL_TIERS = [
    {'title': '35 buyurtma', 'min_rides': 35, 'bonus_amount': 100000, 'order': 1},
    {'title': '55 buyurtma', 'min_rides': 55, 'bonus_amount': 190000, 'order': 2},
    {'title': '80 buyurtma', 'min_rides': 80, 'bonus_amount': 280000, 'order': 3},
    {'title': '100 buyurtma', 'min_rides': 100, 'bonus_amount': 350000, 'order': 4},
]


def set_tiers(apps, schema_editor):
    DriverGoal = apps.get_model('accounts', 'DriverGoal')
    # Eski maqsadlarni o'chirib, faqat shu 4 tarifni faollashtiramiz
    DriverGoal.objects.all().update(is_active=False)
    for tier in GOAL_TIERS:
        DriverGoal.objects.update_or_create(
            min_rides=tier['min_rides'],
            defaults={
                'title': tier['title'],
                'bonus_amount': tier['bonus_amount'],
                'extra_orders_bonus': 10,
                'commission_discount_percent': 2.0,
                'commission_discount_days': 3,
                'period_days': 3,
                'is_active': True,
                'order': tier['order'],
            },
        )


def reverse(apps, schema_editor):
    # Orqaga qaytarish — maqsadlarni o'chirmaymiz (xavfsiz no-op)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_user_referral_balance_referralearning'),
    ]

    operations = [
        migrations.RunPython(set_tiers, reverse),
    ]
