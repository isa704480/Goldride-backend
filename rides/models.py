from django.db import models
from django.conf import settings
from accounts.models import Driver


class Ride(models.Model):
    """A ride that may contain 1-2 passengers (shared ride)."""

    STATUS_CHOICES = [
        ('searching', 'Qidirilmoqda'),
        ('driver_found', 'Haydovchi topildi'),
        ('on_the_way', 'Yo\'lda'),
        ('arrived', 'Yetib keldi'),
        ('started', 'Boshlandi'),
        ('completed', 'Yakunlandi'),
        ('cancelled', 'Bekor qilindi'),
    ]

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rides',
        verbose_name='Haydovchi'
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='searching',
        verbose_name='Status',
        db_index=True
    )
    is_shared = models.BooleanField(default=True, verbose_name='Sherikli safar')
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Jami narx (UZS)'
    )
    total_distance = models.FloatField(
        default=0,
        verbose_name='Jami masofa (km)'
    )
    commission_rate = models.FloatField(
        default=0.05,
        verbose_name='Komissiya stavkasi'
    )
    commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Komissiya miqdori (UZS)'
    )
    driver_earnings = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Haydovchi daromadi (UZS)'
    )
    is_scheduled = models.BooleanField(
        default=False,
        verbose_name='Rejalashtirilgan'
    )
    route_polyline = models.TextField(
        blank=True,
        null=True,
        verbose_name='Marshrut'
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Boshlangan vaqt')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Tugagan vaqt')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqt')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Safar'
        verbose_name_plural = 'Safarlar'
        ordering = ['-created_at']

    def __str__(self):
        return f"Safar #{self.id} - {self.get_status_display()}"

    @property
    def passenger_count(self):
        return self.passengers.count()

    def calculate_commission(self):
        """Calculate commission and driver earnings."""
        self.commission_amount = self.total_price * self.commission_rate
        self.driver_earnings = self.total_price - self.commission_amount
        return self.commission_amount


class RideRequest(models.Model):
    """A request from a passenger for a ride."""

    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('matched', 'Topildi'),
        ('accepted', 'Qabul qilindi'),
        ('arrived', 'Yetib keldi'),
        ('cancelled', 'Bekor qilindi'),
        ('expired', 'Muddati o\'tdi'),
        ('completed', 'Yakunlandi'),
        ('external_pending', 'Tashqi buyurtma kutilmoqda'),
    ]

    SHARE_TYPE_CHOICES = [
        ('solo', 'Yolg\'iz (Chegirmasiz)'),
        ('shared_1', '1 kishi bilan (20% chegirma)'),
        ('shared_2', '2 kishi bilan (30% chegirma)'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ride_requests',
        verbose_name='Yo\'lovchi'
    )
    ride = models.ForeignKey(
        Ride,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests',
        verbose_name='Safar'
    )
    pickup_lat = models.FloatField(verbose_name='Chiqish kengligi')
    pickup_lng = models.FloatField(verbose_name='Chiqish uzunligi')
    pickup_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Chiqish manzili'
    )
    drop_lat = models.FloatField(verbose_name='Tushish kengligi')
    drop_lng = models.FloatField(verbose_name='Tushish uzunligi')
    drop_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Tushish manzili'
    )
    estimated_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Taxminiy narx (UZS)'
    )
    estimated_distance = models.FloatField(
        default=0,
        verbose_name='Taxminiy masofa (km)'
    )
    estimated_duration = models.IntegerField(
        default=0,
        verbose_name='Taxminiy vaqt (min)'
    )
    is_shared = models.BooleanField(
        default=True,
        verbose_name='Sherikli safar'
    )
    share_type = models.CharField(
        max_length=20,
        choices=SHARE_TYPE_CHOICES,
        default='solo',
        verbose_name='Safar turi'
    )
    use_bonus = models.BooleanField(
        default=False,
        verbose_name='Bonusdan foydalanish'
    )
    bonus_percent = models.IntegerField(
        default=100,
        verbose_name='Bonus foizi'
    )
    car_category = models.CharField(
        max_length=20,
        default='economy',
        verbose_name='Tanlangan avto sinfi'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status',
        db_index=True
    )
    is_scheduled = models.BooleanField(
        default=False,
        verbose_name='Rejalashtirilgan'
    )
    scheduled_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Rejalashtirilgan vaqt'
    )
    external_provider = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Tashqi xizmat (Yandex/Fasten/etc)'
    )
    external_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Tashqi buyurtma ID'
    )
    external_eta = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Tashqi xizmat kelish vaqti'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Safar so\'rovi'
        verbose_name_plural = 'Safar so\'rovlari'
        ordering = ['-created_at']

    def __str__(self):
        return f"So'rov #{self.id} - {self.user.phone} - {self.get_status_display()}"


class RidePassenger(models.Model):
    """Links passengers to a ride with their specific pickup/dropoff points."""

    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='passengers',
        verbose_name='Safar'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ride_participations',
        verbose_name='Yo\'lovchi'
    )
    ride_request = models.OneToOneField(
        RideRequest,
        on_delete=models.SET_NULL,
        null=True,
        related_name='passenger_entry',
        verbose_name='So\'rov'
    )
    pickup_lat = models.FloatField(verbose_name='Chiqish kengligi')
    pickup_lng = models.FloatField(verbose_name='Chiqish uzunligi')
    pickup_address = models.CharField(max_length=255, blank=True)
    drop_lat = models.FloatField(verbose_name='Tushish kengligi')
    drop_lng = models.FloatField(verbose_name='Tushish uzunligi')
    drop_address = models.CharField(max_length=255, blank=True)
    fare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Narx (UZS)'
    )
    pickup_order = models.IntegerField(default=1, verbose_name='Chiqish tartibi')
    drop_order = models.IntegerField(default=1, verbose_name='Tushish tartibi')
    picked_up = models.BooleanField(default=False, verbose_name='Olib ketildi')
    dropped_off = models.BooleanField(default=False, verbose_name='Tushirildi')
    picked_up_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True, verbose_name='Yetib kelgan vaqt')
    waiting_penalty = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Kutish jarimasi (UZS)'
    )
    dropped_off_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Yo'lovchi"
        verbose_name_plural = "Yo'lovchilar"
        unique_together = ['ride', 'user']

    def __str__(self):
        return f"Yo'lovchi {self.user.phone} - Safar #{self.ride_id}"


class RideRating(models.Model):
    """Rating after ride completion."""
    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='ratings'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_given'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_received',
        null=True,
        blank=True
    )
    rating = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        verbose_name='Baho'
    )
    comment = models.TextField(blank=True, verbose_name='Izoh')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Baho'
        verbose_name_plural = 'Baholar'
        unique_together = ['ride', 'user', 'target_user']


class RideStop(models.Model):
    """Additional stops for multi-stop rides."""
    ride_request = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name='stops'
    )
    address = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    order = models.IntegerField(default=1)

    class Meta:
        verbose_name = 'Safar to\'xtash joyi'
        verbose_name_plural = 'Safar to\'xtash joylari'
        ordering = ['order']


class ChatMessage(models.Model):
    """In-app chat between driver and passenger."""
    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='chat_messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chat xabari'
        verbose_name_plural = 'Chat xabarlari'
        ordering = ['created_at']


class ServiceZone(models.Model):
    """
    Xizmat ko'rsatish hududi (geofencing).
    Admin panel orqali o'zgartiriladi — kod qayta yozilmaydi.
    """
    name = models.CharField(max_length=100, verbose_name='Hudud nomi')
    is_active = models.BooleanField(default=True, verbose_name='Faol')

    # Chegaralar (to'rtburchak)
    lat_min = models.FloatField(verbose_name='Minimal kenglik (janub)')
    lat_max = models.FloatField(verbose_name='Maksimal kenglik (shimol)')
    lng_min = models.FloatField(verbose_name='Minimal uzunlik (g\'arb)')
    lng_max = models.FloatField(verbose_name='Maksimal uzunlik (sharq)')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Xizmat hududi'
        verbose_name_plural = 'Xizmat hududlari'

    def __str__(self):
        return self.name

    def contains(self, lat, lng):
        """Berilgan koordinata hudud ichida ekanligini tekshirish."""
        return self.lat_min <= lat <= self.lat_max and self.lng_min <= lng <= self.lng_max

    @classmethod
    def is_within_service_area(cls, lat, lng):
        """
        Koordinata birorta faol xizmat hududi ichida ekanligini tekshirish.
        Agar DB da hech qanday faol zona bo'lmasa, settings.py fallback'iga qaytadi.
        """
        zones = cls.objects.filter(is_active=True)
        if zones.exists():
            return any(zone.contains(lat, lng) for zone in zones)

        # Fallback: settings.py dagi hardcoded Toshkent chegaralari
        boundary = getattr(settings, 'TASHKENT_BOUNDARY', {})
        if boundary:
            return (
                boundary['LAT_MIN'] <= lat <= boundary['LAT_MAX'] and
                boundary['LNG_MIN'] <= lng <= boundary['LNG_MAX']
            )
        return True


class ReferralBonus(models.Model):
    """Tracks referral bonuses with a ride threshold."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='earned_bonuses',
        verbose_name='Taklif qilgan'
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_bonus',
        verbose_name='Taklif qilingan'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Bonus miqdori')
    rides_required = models.IntegerField(default=5, verbose_name='Kerakli safarlar soni')
    rides_completed = models.IntegerField(default=0, verbose_name='Bajarilgan safarlar')
    is_paid = models.BooleanField(default=False, verbose_name='To\'langan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Referal bonus'
        verbose_name_plural = 'Referal bonuslar'

    def __str__(self):
        return f"{self.user.phone} -> {self.referred_user.phone} ({self.rides_completed}/{self.rides_required})"


class EmergencyAlert(models.Model):
    """Panic Button (SOS) alerts."""
    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='emergency_alerts',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='emergency_alerts'
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Faol'),
            ('resolved', 'Hal qilindi'),
            ('false_alarm', 'Xato signal'),
        ],
        default='active'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'SOS Signal'
        verbose_name_plural = 'SOS Signallar'
        ordering = ['-created_at']

    def __str__(self):
        return f"SOS - {self.user.phone} ({self.created_at})"
