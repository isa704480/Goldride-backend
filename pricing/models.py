from django.db import models


class PricingRule(models.Model):
    """Admin-configurable pricing rules."""

    name = models.CharField(max_length=50, unique=True, verbose_name='Nomi')
    base_fare = models.IntegerField(default=5000, verbose_name='Boshlang\'ich narx (UZS)')
    per_km_rate = models.IntegerField(default=2000, verbose_name='Har km narxi (UZS)')
    shared_discount = models.FloatField(default=0.30, verbose_name='Sherikli chegirma (%)')
    commission_rate = models.FloatField(default=0.05, verbose_name='Komissiya stavkasi (%)')
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
