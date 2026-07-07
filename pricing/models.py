from django.db import models


def default_tariff_categories():
    """Avtomobil klasslari bo'yicha tariflar (engine.py bilan bir xil standart qiymatlar).
    base — chaqirish narxi, km — har km, per_min — har daqiqa,
    disc_1 — 1 sherik uchun maksimal chegirma, disc_2 — 2 sherik uchun maksimal chegirma."""
    return {
        'economy':  {'label': 'Start',           'base': 6000,  'km': 1500, 'per_min': 200, 'disc_1': 0.15, 'disc_2': 0.30},
        'comfort':  {'label': 'Komfort',         'base': 7000,  'km': 2000, 'per_min': 250, 'disc_1': 0.15, 'disc_2': 0.30},
        'electro':  {'label': 'Elektro Komfort', 'base': 7500,  'km': 2300, 'per_min': 280, 'disc_1': 0.20, 'disc_2': 0.40},
        'business': {'label': 'Business',        'base': 10000, 'km': 2800, 'per_min': 350, 'disc_1': 0.20, 'disc_2': 0.40},
    }


class PricingRule(models.Model):
    """Admin-configurable pricing rules."""

    name = models.CharField(max_length=50, unique=True, verbose_name='Nomi')
    base_fare = models.IntegerField(default=5000, verbose_name='Boshlang\'ich narx (UZS)')
    per_km_rate = models.IntegerField(default=2000, verbose_name='Har km narxi (UZS)')
    shared_discount = models.FloatField(default=0.30, verbose_name='Sherikli chegirma (%)')
    commission_rate = models.FloatField(default=0.20, verbose_name='Komissiya stavkasi (%)')
    # Avtomobil klasslari bo'yicha tariflar (start/komfort/elektro/business)
    categories = models.JSONField(default=default_tariff_categories, blank=True, verbose_name='Klass tariflari')
    waiting_rate_per_min = models.IntegerField(default=500, verbose_name='Kutish narxi (minutiga, UZS)')
    cancellation_fee = models.IntegerField(default=2000, verbose_name='Bekor qilish jarimasi (UZS)')
    min_fare = models.IntegerField(default=3000, verbose_name='Minimal narx (UZS)')
    multi_stop_fee = models.IntegerField(default=2000, verbose_name='Qo\'shimcha to\'xtash narxi (UZS)')
    scheduled_fee = models.IntegerField(default=5000, verbose_name='Oldindan band qilish narxi (UZS)')
    is_active = models.BooleanField(default=True, verbose_name='Faol')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Narx qoidasi'
        verbose_name_plural = 'Narx qoidalari'

    def __str__(self):
        return self.name
