from django.db import migrations

GOALS = [
    {'title': '35 buyurtma',  'min_rides': 35,  'bonus_amount': 100000, 'extra_orders_bonus': 10, 'commission_discount_percent': 2.0, 'commission_discount_days': 3, 'period_days': 3, 'is_active': True, 'order': 1},
    {'title': '55 buyurtma',  'min_rides': 55,  'bonus_amount': 190000, 'extra_orders_bonus': 10, 'commission_discount_percent': 2.0, 'commission_discount_days': 3, 'period_days': 3, 'is_active': True, 'order': 2},
    {'title': '80 buyurtma',  'min_rides': 80,  'bonus_amount': 280000, 'extra_orders_bonus': 10, 'commission_discount_percent': 2.0, 'commission_discount_days': 3, 'period_days': 3, 'is_active': True, 'order': 3},
    {'title': '100 buyurtma', 'min_rides': 100, 'bonus_amount': 350000, 'extra_orders_bonus': 10, 'commission_discount_percent': 2.0, 'commission_discount_days': 3, 'period_days': 3, 'is_active': True, 'order': 4},
]


def seed_goals(apps, schema_editor):
    DriverGoal = apps.get_model('accounts', 'DriverGoal')
    for g in GOALS:
        DriverGoal.objects.get_or_create(min_rides=g['min_rides'], defaults=g)


def remove_goals(apps, schema_editor):
    DriverGoal = apps.get_model('accounts', 'DriverGoal')
    DriverGoal.objects.filter(min_rides__in=[35, 55, 80, 100]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_cashback_goals_telegram_otp'),
    ]

    operations = [
        migrations.RunPython(seed_goals, remove_goals),
    ]
