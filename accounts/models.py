import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator


phone_regex = RegexValidator(
    regex=r'^\+998\d{9}$',
    message="Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak."
)

plate_regex = RegexValidator(
    regex=r'^(?:\d{2}[A-Z]\d{3}[A-Z]{2}|\d{2}\d{3}[A-Z]{3})$',
    message="Davlat raqami noto'g'ri formatda (Masalan: 01A123AA yoki 01123AAA)."
)


class User(AbstractUser):
    """Custom user model with phone-based authentication."""

    ROLE_CHOICES = [
        ('passenger', 'Yo\'lovchi'),
        ('driver', 'Haydovchi'),
    ]

    LANG_CHOICES = [
        ('uz', "O'zbekcha"),
        ('ru', 'Русский'),
        ('en', 'English'),
    ]

    phone = models.CharField(
        max_length=13,
        unique=True,
        validators=[phone_regex],
        verbose_name='Telefon raqami'
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='passenger',
        verbose_name='Rol'
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        verbose_name='Rasm'
    )
    language = models.CharField(
        max_length=2,
        choices=LANG_CHOICES,
        default='uz',
        verbose_name='Til'
    )
    id_number = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name='ID raqami'
    )
    passenger_rating = models.FloatField(default=5.0, verbose_name='Yo\'lovchi reytingi')
    total_passenger_rides = models.IntegerField(default=0, verbose_name='Jami yo\'lovchi safarlari')
    is_verified = models.BooleanField(default=False, verbose_name='Tasdiqlangan')
    is_active = models.BooleanField(default=True)
    penalty_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        verbose_name='Jarima balansi (UZS)'
    )
    bonus_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Bonus balansi (UZS)'
    )
    cancellation_count = models.IntegerField(
        default=0,
        verbose_name='Ketma-ket bekor qilishlar soni'
    )
    last_cancellation_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Oxirgi bekor qilish vaqti'
    )
    is_blocked = models.BooleanField(
        default=False,
        verbose_name='Bloklangan'
    )
    gold_points = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='GoldPoints'
    )
    referral_code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name='Referal kod'
    )
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals',
        verbose_name='Taklif qilgan foydalanuvchi'
    )
    referral_rides_count = models.IntegerField(
        default=0,
        verbose_name='Do\'stining safarlari soni (Referal uchun)'
    )
    pending_referral_bonus = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Kutilayotgan referal bonus (UZS)'
    )
    bank_account_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name='Bank hisob raqami'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Anti-fraud fields
    device_id = models.CharField(max_length=255, blank=True, null=True)
    last_ip = models.GenericIPAddressField(blank=True, null=True)
    telegram_username = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name='Telegram username'
    )
    telegram_chat_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True,
        verbose_name='Telegram Chat ID'
    )
    has_agreed_to_terms = models.BooleanField(
        default=False,
        verbose_name='Shartnomaga rozilik'
    )

    def add_gold_points(self, points):
        """Helper to add points safely."""
        self.gold_points += points
        self.save(update_fields=['gold_points'])

    # Use phone as the login field
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # After first save, if id_number is not set, generate random 6-digit
        if not self.id_number:
            import random
            while True:
                rand_id = random.randint(100000, 999999)
                if not type(self).objects.filter(id_number=rand_id).exists():
                    self.id_number = rand_id
                    break
            self.save(update_fields=['id_number'])

        if not self.referral_code:
            self.referral_code = f"GOLD{self.id_number}"
            self.save(update_fields=['referral_code'])

    def add_gold_points(self, amount):
        """Adds GoldPoints to user balance."""
        self.gold_points += amount
        self.save(update_fields=['gold_points'])

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_full_name() or self.phone} ({self.get_role_display()})"


class Driver(models.Model):
    """Extended profile for drivers."""

    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
        ('blocked', 'Bloklangan'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='driver_profile',
        verbose_name='Foydalanuvchi'
    )
    license_number = models.CharField(
        max_length=20,
        verbose_name='Haydovchilik guvohnomasi'
    )
    license_photo = models.ImageField(
        upload_to='licenses/',
        null=True,
        blank=True,
        verbose_name='Guvohnoma rasmi (Oldi)'
    )
    license_photo_back = models.ImageField(
        upload_to='licenses/',
        null=True,
        blank=True,
        verbose_name='Guvohnoma rasmi (Orqa)'
    )
    passport_photo_front = models.ImageField(
        upload_to='passports/',
        null=True,
        blank=True,
        verbose_name='Pasport rasmi (Oldi)'
    )
    passport_photo_back = models.ImageField(
        upload_to='passports/',
        null=True,
        blank=True,
        verbose_name='Pasport rasmi (Orqa)'
    )
    face_id_photo = models.ImageField(
        upload_to='face_id/',
        null=True,
        blank=True,
        verbose_name='Face ID rasmi'
    )
    taxi_license_photo = models.FileField(
        upload_to='taxi_licenses/',
        null=True,
        blank=True,
        verbose_name='Taksi litsenziyasi (PDF/Rasm)'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    is_online = models.BooleanField(default=False, verbose_name='Onlayn')
    is_being_requested = models.BooleanField(
        default=False,
        verbose_name='So\'rov kutilmoqda',
        help_text='True bo\'lsa, haydovchi hozir yangi so\'rov kutmoqda — boshqa so\'rov yuborilmaydi.'
    )
    current_lat = models.FloatField(null=True, blank=True, verbose_name='Kenglik')
    current_lng = models.FloatField(null=True, blank=True, verbose_name='Uzunlik')
    rating = models.FloatField(default=5.0, verbose_name='Reyting')
    total_rides = models.IntegerField(default=0, verbose_name='Jami safarlar')
    total_rides_completed = models.IntegerField(default=0, verbose_name='Tugatilgan safarlar')
    total_requests_received = models.IntegerField(default=0, verbose_name='Qabul qilingan so\'rovlar')
    total_earnings = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Jami daromad (UZS)'
    )
    commission_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Komissiya to\'langan (UZS)'
    )

    # Kirish davri komissiyasi: dastlabki 15 buyurtma yoki 48 soat (kamida 8 ta)
    intro_period_completed = models.BooleanField(
        default=False,
        verbose_name='Kirish davri tugagan',
        help_text='True bo\'lsa, oddiy komissiya qo\'llanadi'
    )
    intro_period_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Kirish davri boshlangan vaqt'
    )

    # Maqsad chegirmasi: maqsad bajarilgandan keyin N kunlik -2% komissiya
    commission_discount_until = models.DateField(
        null=True, blank=True,
        verbose_name='Komissiya chegirmasi (gacha)'
    )
    commission_discount_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default=0,
        verbose_name='Komissiya chegirmasi (%)'
    )

    # Referral — faqat haydovchi boshqa haydovchini taklif qila oladi
    referred_by_driver = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referred_drivers',
        verbose_name='Taklif qilgan haydovchi'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Haydovchi'
        verbose_name_plural = 'Haydovchilar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_status_display()}"

    @property
    def net_earnings(self):
        return self.total_earnings - self.commission_paid


class Vehicle(models.Model):
    """Vehicle details for a driver."""

    TYPE_CHOICES = [
        ('sedan', 'Sedan'),
        ('minivan', 'Minivan'),
        ('suv', 'SUV'),
        ('hatchback', 'Xetchbek'),
    ]

    COLOR_CHOICES = [
        ('white', 'Oq'),
        ('black', 'Qora'),
        ('silver', 'Kumush'),
        ('grey', 'Kulrang'),
        ('red', 'Qizil'),
        ('blue', "Ko'k"),
        ('green', 'Yashil'),
        ('yellow', 'Sariq'),
        ('other', 'Boshqa'),
    ]

    CLASS_CHOICES = [
        ('economy', 'Ekonom'),
        ('comfort', 'Komfort'),
        ('business', 'Biznes'),
        ('electro', 'Elektro'),
    ]

    # AI auto-classification rules based on user criteria
    BUSINESS_MODELS = [
        'malibu 2', 'k5', 'k8', 'grandeur', 'e-class', '5 series', 'es', 's-class', 'cls', 'gle', 'gls', 
        'x5', 'x6', 'x7', 'a6', 'a7', 'a8', 'q7', 'q8', 'macan', 'cayenne', 'panamera', 
        'navigator', 'escalade', 'land cruiser', 'prado', 'lx', 'rx', 'gx',
        'мерседес e', 'бмв 5', 'лексус es'
    ]

    ELECTRO_MODELS = [
        'zeekr 001', 'zeekr 009', 'tesla model s', 'tesla model x', 'byd han',
        'byd song', 'byd yuan', 'byd chazor', 'zeekr x', 'byd seagull',
        'chery eq', 'hongqi', 'nio', 'li auto'
    ]

    COMFORT_MODELS = [
        'malibu', 'sonata', 'octavia', 'jetta', 'optima', 'elantra',
        'tucson', 'santa fe', 'sportage', 'sorento', 'equinox', 'traverse', 'captiva',
        'tracker', 'tracker 2', 'monza', 'onix', 'epica',
        'cr-v', 'accord', 'civic', 'passat', 'tiguan', 'c-class', '3 series',
        'chery tiggo', 'haval',
        'малибу', 'соната', 'оптима', 'оникс', 'трекер'
    ]

    ECONOM_MODELS = [
        'cobalt', 'nexia 3', 'nexia', 'spark', 'matiz', 'lacetti', 'gentra',
        'accent', 'rio', 'polo', 'logan', 'solaris', 'rapid', 'aveo', 'cruze',
        'lada', 'granta', 'vesta', 'priora', 'kalina', 'largus', 'niva', 
        'zaz', 'gaz', 'volga',
        'кобальт', 'нексия', 'спарк', 'матиз', 'ласетти', 'джентра', 
        'акцент', 'рио', 'поло', 'солярис', 'лада', 'гранта', 'веста', 'приора', 'ваз'
    ]

    driver = models.OneToOneField(
        Driver,
        on_delete=models.CASCADE,
        related_name='vehicle',
        verbose_name='Haydovchi'
    )
    make = models.CharField(
        max_length=50, 
        validators=[RegexValidator(regex=r'^[a-zA-Z0-9\s\-а-яА-ЯёЁ]{2,50}$', message="Marka kamida 2 ta harf yoki raqamdan iborat bo'lishi kerak")],
        verbose_name='Marka'
    )
    model = models.CharField(
        max_length=50, 
        validators=[RegexValidator(regex=r'^[a-zA-Z0-9\s\-а-яА-ЯёЁ]{2,50}$', message="Model kamida 2 ta harf yoki raqamdan iborat bo'lishi kerak")],
        verbose_name='Model'
    )
    year = models.IntegerField(verbose_name='Yil')
    color = models.CharField(
        max_length=10,
        choices=COLOR_CHOICES,
        verbose_name='Rang'
    )
    plate_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[plate_regex],
        verbose_name='Davlat raqami'
    )
    vehicle_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='sedan',
        verbose_name='Turi'
    )
    car_class = models.CharField(
        max_length=10,
        choices=CLASS_CHOICES,
        default='economy',
        verbose_name='Sinf (Ekonom/Komfort/Biznes)'
    )
    photo = models.ImageField(
        upload_to='vehicles/',
        null=True,
        blank=True,
        verbose_name='Mashina rasmi (Oldi)'
    )
    photo_back = models.ImageField(
        upload_to='vehicles/',
        null=True,
        blank=True,
        verbose_name='Mashina rasmi (Orqa)'
    )
    photo_left = models.ImageField(
        upload_to='vehicles/',
        null=True,
        blank=True,
        verbose_name='Mashina rasmi (Chap)'
    )
    photo_right = models.ImageField(
        upload_to='vehicles/',
        null=True,
        blank=True,
        verbose_name='Mashina rasmi (O\'ng)'
    )
    interior_photo_1 = models.ImageField(
        upload_to='vehicles/interior/',
        null=True,
        blank=True,
        verbose_name='Salon rasmi 1'
    )
    interior_photo_2 = models.ImageField(
        upload_to='vehicles/interior/',
        null=True,
        blank=True,
        verbose_name='Salon rasmi 2'
    )
    tech_passport_photo_front = models.ImageField(
        upload_to='tech_passports/',
        null=True,
        blank=True,
        verbose_name='Texpasport rasmi (Oldi)'
    )
    tech_passport_photo_back = models.ImageField(
        upload_to='tech_passports/',
        null=True,
        blank=True,
        verbose_name='Texpasport rasmi (Orqa)'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def classify_vehicle(self):
        """Precise car class detection from make, model, and year."""
        model_lower = self.model.lower().strip()

        # 1. Toyota Camry rule
        if 'camry' in model_lower:
            if self.year >= 2018:
                return 'business'
            elif self.year >= 2015:
                return 'comfort'
            else:
                return 'economy'

        # 2. Check Electro
        if any(m in model_lower for m in self.ELECTRO_MODELS):
            return 'electro'

        # 3. Cobalt and Gentra rules
        if 'gentra' in model_lower or 'cobalt' in model_lower or 'кобальт' in model_lower or 'джентра' in model_lower:
            if self.year >= 2020:
                return 'comfort'
            return 'economy'

        # 4. Check Business
        if any(m in model_lower for m in self.BUSINESS_MODELS) and self.year >= 2018:
            return 'business'

        # 5. Check Comfort
        if any(m in model_lower for m in self.COMFORT_MODELS) and self.year >= 2015:
            return 'comfort'

        # 6. Default to Econom if >= 2005 (or fallback)
        return 'economy'

    def save(self, *args, **kwargs):
        # Auto-classify on save if not manually set or if make/model changed
        if not self.pk or not self.car_class:
            self.car_class = self.classify_vehicle()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Mashina'
        verbose_name_plural = 'Mashinalar'

    def __str__(self):
        return f"{self.make} {self.model} ({self.plate_number}) [{self.get_car_class_display()}]"


class SavedLocation(models.Model):
    """User's saved/favorite locations (Uy, Ish, etc.)."""

    ICON_CHOICES = [
        ('home', 'Uy'),
        ('briefcase', 'Ish'),
        ('star', 'Sevimli'),
        ('school', 'Maktab'),
        ('location', 'Boshqa'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='saved_locations',
        verbose_name='Foydalanuvchi'
    )
    name = models.CharField(max_length=100, verbose_name='Nomi')
    address = models.CharField(max_length=255, verbose_name='Manzil')
    latitude = models.FloatField(verbose_name='Kenglik')
    longitude = models.FloatField(verbose_name='Uzunlik')
    icon = models.CharField(
        max_length=20,
        choices=ICON_CHOICES,
        default='location',
        verbose_name='Ikonka'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Saqlangan manzil'
        verbose_name_plural = 'Saqlangan manzillar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.phone} — {self.name}: {self.address}"


class FavoriteDriver(models.Model):
    """Passenger's favorite drivers."""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favorite_drivers'
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sevimli haydovchi'
        verbose_name_plural = 'Sevimli haydovchilar'
        unique_together = ['user', 'driver']


class Badge(models.Model):
    """Driver badges/achievements."""
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="Icon name for mobile app")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Nishon'
        verbose_name_plural = 'Nishonlar'

    def __str__(self):
        return self.name


class DriverBadge(models.Model):
    """Badges earned by drivers."""
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name='badges'
    )
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Haydovchi nishoni'
        verbose_name_plural = 'Haydovchi nishonlari'
        unique_together = ['driver', 'badge']


class DriverGoal(models.Model):
    """
    3 kunlik maqsad tizimi.
    Haydovchi maqsadni OLDINDAN tanlashi kerak.
    Bajarilganda: bonus + qo'shimcha 10 buyurtma + keyingi 3 kun -2% komissiya.
    """
    title = models.CharField(max_length=100, default='', verbose_name='Nomi')
    min_rides = models.IntegerField(default=0, verbose_name='Kerakli buyurtmalar soni')
    bonus_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Pul mukofoti (UZS)'
    )
    extra_orders_bonus = models.IntegerField(
        default=10,
        verbose_name='Qo\'shimcha buyurtmalar bonusi'
    )
    commission_discount_percent = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.0,
        verbose_name='Komissiya chegirmasi (%)'
    )
    commission_discount_days = models.IntegerField(
        default=3,
        verbose_name='Komissiya chegirmasi davomiyligi (kun)'
    )
    period_days = models.IntegerField(
        default=3,
        verbose_name='Maqsad davri (kun)'
    )
    is_active = models.BooleanField(default=True, verbose_name='Faol')
    order = models.IntegerField(default=0, verbose_name='Tartib')

    class Meta:
        verbose_name = 'Haydovchi maqsadi'
        verbose_name_plural = 'Haydovchi maqsadlari'
        ordering = ['min_rides']

    def __str__(self):
        return f"{self.title}: {self.min_rides} buyurtma → {self.bonus_amount:,.0f} UZS"


class GoalProgress(models.Model):
    """
    Haydovchining tanlangan maqsad bo'yicha taraqqiyoti.
    Maqsad oldindan tanlanadi, 3 kun davomida bajarilishi kerak.
    """
    STATUS_CHOICES = [
        ('active', 'Faol'),
        ('completed', 'Bajarildi'),
        ('failed', 'Bajarilmadi'),
    ]

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name='goal_progress'
    )
    goal = models.ForeignKey(
        DriverGoal,
        on_delete=models.CASCADE
    )
    current_count = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='active',
        verbose_name='Holat'
    )
    start_date = models.DateField(null=True, blank=True, verbose_name='Boshlash sanasi')
    end_date = models.DateField(null=True, blank=True, verbose_name='Tugash sanasi')
    reward_paid = models.BooleanField(default=False, verbose_name='Mukofot berildi')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Maqsad taraqqiyoti'
        verbose_name_plural = 'Maqsadlar taraqqiyoti'

    def __str__(self):
        return f"{self.driver.user.phone} — {self.goal.title} ({self.status})"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now().date() > self.end_date and self.status == 'active'

class Wallet(models.Model):
    """Virtual wallet for 'Oltin tanga' currency."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wallet',
        verbose_name='Foydalanuvchi'
    )
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name='Balans (Oltin tanga)'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def deposit(self, amount, description='Hisobni to\'ldirish'):
        from django.db import transaction
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.save()
            
            # Automatic GoldPoints: 1000 UZS = 1 Ball
            points = int(amount / 1000)
            if points > 0:
                user = User.objects.select_for_update().get(pk=wallet.user.pk)
                user.gold_points += points
                user.save()

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='topup',
                amount=amount,
                description=description,
                status='completed'
            )
            # Update self balance to reflect the database change
            self.balance = wallet.balance

    def withdraw(self, amount, description='Mablag\' yechish'):
        from django.db import transaction
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance >= amount:
                wallet.balance -= amount
                wallet.save()
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='payment',
                    amount=-amount,
                    description=description,
                    status='completed'
                )
                # Update self balance to reflect the database change
                self.balance = wallet.balance
                return True
            return False

    class Meta:
        verbose_name = 'Hamyon'
        verbose_name_plural = 'Hamyonlar'

    def __str__(self):
        return f"{self.user.phone} - {self.balance} tanga"


class WalletTransaction(models.Model):
    """Transaction history for wallets."""
    
    TYPE_CHOICES = [
        ('topup', 'To\'ldirish'),
        ('payment', 'To\'lov'),
        ('withdraw', 'Yechish'),
        ('refund', 'Qaytarish'),
        ('bonus', 'Bonus'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('completed', 'Bajarildi'),
        ('failed', 'Xato'),
    ]
    
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name='Hamyon'
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        verbose_name='Turi'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Miqdor'
    )
    description = models.CharField(
        max_length=255,
        verbose_name='Tavsif'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Status'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tranzaksiya'
        verbose_name_plural = 'Tranzaksiyalar'
        ordering = ['-created_at']

    def rollback(self):
        """Rollback a transaction if it was already completed."""
        if self.status != 'completed':
            return False
            
        wallet = self.wallet
        if self.transaction_type == 'payment' or self.transaction_type == 'withdraw':
            # Add back the money
            wallet.balance += self.amount
            wallet.save()
            self.status = 'failed'
            self.description += " (Qaytarildi/Rollback)"
            self.save()
            return True
        elif self.transaction_type == 'topup' or self.transaction_type == 'bonus':
            # Deduct the money (if possible)
            if wallet.balance >= self.amount:
                wallet.balance -= self.amount
                wallet.save()
                self.status = 'failed'
                self.description += " (Bekor qilindi/Rollback)"
                self.save()
                return True
        return False

    def __str__(self):
        return f"{self.wallet.user.phone} - {self.transaction_type}: {self.amount}"

class WalletRequest(models.Model):
    """Requests for deposit or withdrawal that need admin approval."""
    TYPE_CHOICES = [
        ('deposit', 'To\'ldirish'),
        ('withdraw', 'Yechish'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_requests')
    request_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hamyon so\'rovi'
        verbose_name_plural = 'Hamyon so\'rovlari'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.phone} - {self.request_type} - {self.amount}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            old_status = WalletRequest.objects.get(pk=self.pk).status

        super().save(*args, **kwargs)

        # If status changed to approved
        if old_status == 'pending' and self.status == 'approved':
            from django.db import transaction
            with transaction.atomic():
                wallet, created = Wallet.objects.get_or_create(user=self.user)
                if self.request_type == 'deposit':
                    wallet.deposit(self.amount, description=f"Hamyon to'ldirildi (So'rov #{self.id})")
                elif self.request_type == 'withdraw':
                    if not wallet.withdraw(self.amount, description=f"Mablag' yechildi (So'rov #{self.id})"):
                        pass


class TelegramOTP(models.Model):
    """
    Telegram bot orqali yuborilgan OTP kodlarini DB'da saqlash.
    Bu bot va veb-server alohida processda ishlayotganda ham ishlaydi
    (memory cache'dan farqli).
    """
    phone = models.CharField(max_length=13, db_index=True, verbose_name='Telefon raqami')
    otp = models.CharField(max_length=6, verbose_name='OTP kodi')
    chat_id = models.CharField(max_length=20, blank=True, verbose_name='Telegram Chat ID')
    expires_at = models.DateTimeField(verbose_name='Amal qilish muddati')
    is_used = models.BooleanField(default=False, verbose_name='Ishlatilgan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Telegram OTP'
        verbose_name_plural = 'Telegram OTPlar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone} — {self.otp}"

    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and self.expires_at > timezone.now()

    @classmethod
    def create_otp(cls, phone, chat_id=''):
        import random
        from django.utils import timezone
        from datetime import timedelta
        cls.objects.filter(phone=phone, is_used=False).update(is_used=True)
        otp = str(random.randint(100000, 999999))
        return cls.objects.create(
            phone=phone,
            otp=otp,
            chat_id=str(chat_id),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    @classmethod
    def verify(cls, phone, otp):
        entry = cls.objects.filter(phone=phone, otp=otp, is_used=False).first()
        if entry and entry.is_valid():
            entry.is_used = True
            entry.save(update_fields=['is_used'])
            return entry
        return None
