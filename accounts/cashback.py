"""
Goldride — Cashback va Bonus tizimi

Mijoz qoidalari:
  - 1-5 safar:  karta → 40% keshbek,  naqd → 15% keshbek
  - 6+ safar:   2% doimiy keshbek (istalgan to'lov)
  - Bonuslar 6-safardan boshlab ishlatish mumkin
  - Maksimum 70% to'lovni bonusdan to'lash mumkin

Do'st taklif qoidalari:
  - Do'stining har safaridan: naqd → 1%, karta → 2% bonus
  - Bonuslar ERTANGI KUN tushadi (pending_referral_bonus orqali)
  - Referral bonusni kartaga yechish: 2% komissiya, min 1000 UZS qolishi kerak

Haydovchi komissiya qoidalari (YANGILANGAN):
  Park haydovchilari uchun:
    - Birinchi 30 kun (ro'yxatdan o'tgan kundan): 2% komissiya
    - 30 kundan keyin: 1.5% komissiya
  Solo haydovchilar uchun:
    - Kirish davri (dastlabki 15 ta yoki 48soat+8ta): 20% (elektro: 19%)
    - Ertalab 07-09: 16% (elektro: 15%)
    - Oddiy: settings.PRICING['COMMISSION_RATE'] (5%)
    - Maqsad chegirmasi: commission_discount_rate % past
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('accounts')

# ---------------------------------------------------------------------------
# Mijoz keshbek
# ---------------------------------------------------------------------------

CASHBACK_INTRO_CARD = Decimal('0.40')   # 1-5 safar, karta
CASHBACK_INTRO_CASH = Decimal('0.15')   # 1-5 safar, naqd
CASHBACK_REGULAR   = Decimal('0.02')    # 6+ safar
INTRO_RIDE_LIMIT   = 5                  # Kirish davri buyurtmalar soni
MAX_BONUS_USAGE    = Decimal('0.70')    # Bonusdan maksimal foydalanish ulushi

REFERRAL_BONUS_CASH = Decimal('0.01')        # Mijoz do'sti naqd to'lasa
REFERRAL_BONUS_CARD = Decimal('0.02')        # Mijoz do'sti karta bilan to'lasa
DRIVER_REFERRAL_RATE = Decimal('0.005')      # Haydovchi referal: 0.5% har safar
REFERRAL_WITHDRAWAL_FEE = Decimal('0.02')    # Yechib olishda komissiya
REFERRAL_MIN_BALANCE = Decimal('1000')       # Yechib olgandan keyin min qoldiq


def get_passenger_cashback_rate(user, payment_method: str) -> Decimal:
    """
    Mijozning joriy keshbek stavkasini hisoblash.
    total_passenger_rides: hozirgacha bajarilgan safarlar (shu safardan oldingi).
    """
    ride_num = (user.total_passenger_rides or 0) + 1

    if ride_num > INTRO_RIDE_LIMIT:
        return CASHBACK_REGULAR

    if payment_method == 'card':
        return CASHBACK_INTRO_CARD
    return CASHBACK_INTRO_CASH


def apply_passenger_cashback(user, fare: Decimal, payment_method: str) -> Decimal:
    """
    Safardan keyin mijozga keshbek yozish.

    Keshbek `bonus_balance` ga tushadi (safar to'lovida ishlatish uchun, max 70%,
    6-safardan boshlab) — referal balansi bilan ARALASHMAYDI.
    Qaytarish: yozilgan keshbek miqdori.
    """
    rate = get_passenger_cashback_rate(user, payment_method)
    cashback = (fare * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    if cashback <= 0:
        return Decimal('0')

    user.bonus_balance = (user.bonus_balance or Decimal('0')) + cashback
    user.save(update_fields=['bonus_balance'])

    ride_num = (user.total_passenger_rides or 0) + 1
    logger.info(
        "Keshbek (bonus_balance): %s → %d UZS (%.0f%%, %d-safar, %s)",
        user.phone, cashback, rate * 100, ride_num, payment_method
    )
    return cashback


def is_bonus_usable(user) -> bool:
    """Mijoz bonuslardan foydalana oladimi? (6-safardan keyin)"""
    return (user.total_passenger_rides or 0) >= INTRO_RIDE_LIMIT


def queue_referral_bonus(referrer, passenger, fare: Decimal, payment_method: str):
    """
    Do'stining safaridan referral bonusni ERTAGA uchun navbatga qo'yish.
    pending_referral_bonus ga yoziladi; har bir hodisa ReferralEarning'ga
    log qilinadi ("kimdan qancha"). Cron flush_pending_referral_bonuses orqali
    referral_balance ga o'tkaziladi.
    """
    from accounts.models import ReferralEarning

    rides_count = (passenger.referral_rides_count or 0) + 1
    if rides_count <= 10:
        rate = Decimal('0.05')
    else:
        rate = REFERRAL_BONUS_CARD if payment_method == 'card' else REFERRAL_BONUS_CASH
        
    bonus = (fare * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    if bonus <= 0:
        return

    referrer.pending_referral_bonus = (referrer.pending_referral_bonus or Decimal('0')) + bonus
    referrer.save(update_fields=['pending_referral_bonus'])

    ReferralEarning.objects.create(
        user=referrer,
        from_user=passenger,
        amount=bonus,
        source='passenger',
        payment_method=payment_method,
        is_credited=False,
    )

    logger.info(
        "Referral bonus navbatga qo'shildi: %s ← %s dan %d UZS (ertaga tushadi)",
        referrer.phone, passenger.phone, bonus
    )


def flush_pending_referral_bonuses():
    """
    Har kuni ertalab ishga tushiriladi (Celery/cron).
    pending_referral_bonus > 0 bo'lgan foydalanuvchilarning bonusini
    referral_balance ga o'tkazadi (hamyon/keshbek bilan aralashmaydi).
    """
    from accounts.models import User, ReferralEarning
    from django.db import transaction

    users = User.objects.filter(pending_referral_bonus__gt=0)
    total_paid = 0
    for user in users:
        with transaction.atomic():
            amount = user.pending_referral_bonus
            user.referral_balance = (user.referral_balance or Decimal('0')) + amount
            user.pending_referral_bonus = Decimal('0')
            user.save(update_fields=['referral_balance', 'pending_referral_bonus'])
            ReferralEarning.objects.filter(user=user, is_credited=False).update(is_credited=True)
        total_paid += 1

    logger.info("Referral bonuslar referral_balance ga o'tkazildi: %d foydalanuvchi", total_paid)
    return total_paid


def withdraw_referral_bonus(user, amount: Decimal) -> tuple[bool, str]:
    """
    Referral balansni kartaga (hamyonga) yechib olish.
    Shartlar: 2% komissiya, yechib olgandan keyin referral_balance'da min 1000 UZS qolishi kerak.
    """
    from accounts.models import Wallet
    from django.db import transaction

    commission = (amount * REFERRAL_WITHDRAWAL_FEE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    total_deduct = amount + commission

    with transaction.atomic():
        u = type(user).objects.select_for_update().get(pk=user.pk)
        current = u.referral_balance or Decimal('0')

        if current - total_deduct < REFERRAL_MIN_BALANCE:
            needed = total_deduct + REFERRAL_MIN_BALANCE
            return False, (
                f"Yetarli referal balans yo'q. Yechish uchun referal balansingizda kamida "
                f"{int(needed):,} UZS bo'lishi kerak (Minimal qoldiq: {int(REFERRAL_MIN_BALANCE):,} UZS)."
            )

        # Referal balansdan yechib, sof miqdorni hamyonga (kartaga) o'tkazamiz
        u.referral_balance = current - total_deduct
        u.save(update_fields=['referral_balance'])

        wallet, _ = Wallet.objects.get_or_create(user=u)
        wallet.deposit(amount, f"Referal bonus yechildi: {int(amount):,} UZS (komissiya {int(commission):,})")

    return True, f"{int(amount):,} UZS hamyoningizga o'tkazildi (komissiya: {int(commission):,} UZS)"


def queue_driver_referral_bonus(referring_driver, fare: Decimal):
    """
    Haydovchi referal bonusi: taklif qilgan haydovchiga
    yangi haydovchi va yo'lovchining har safaridan 0.5% bonus.
    Bonus pending_referral_bonus orqali ertaga tushadi.
    """
    from accounts.models import ReferralEarning

    bonus = (fare * DRIVER_REFERRAL_RATE).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if bonus <= 0:
        return

    referring_driver.user.pending_referral_bonus = (
        referring_driver.user.pending_referral_bonus or Decimal('0')
    ) + bonus
    referring_driver.user.save(update_fields=['pending_referral_bonus'])

    ReferralEarning.objects.create(
        user=referring_driver.user,
        from_user=None,
        amount=bonus,
        source='driver',
        payment_method='',
        is_credited=False,
    )

    logger.info(
        "Haydovchi referal bonus: %s → %d UZS (ertaga tushadi)",
        referring_driver.user.phone, bonus
    )


# ---------------------------------------------------------------------------
# Haydovchi komissiya
# ---------------------------------------------------------------------------

INTRO_COMMISSION_DEFAULT  = Decimal('0.20')   # 20% — dastlabki davr
INTRO_COMMISSION_ELECTRO  = Decimal('0.19')   # 19% — elektro
HAPPY_COMMISSION_DEFAULT  = Decimal('0.16')   # Ertalab 07-09
HAPPY_COMMISSION_ELECTRO  = Decimal('0.15')   # Ertalab 07-09, elektro

INTRO_MAX_RIDES = 15       # Kirish davri tugash chegarasi (buyurtmalar)
INTRO_HOURS     = 48       # Kirish davri tugash chegarasi (soat)
INTRO_MIN_RIDES = 8        # 48 soatda minimal buyurtmalar soni

# Taksi park komissiya qoidalari (yangi)
PARK_COMMISSION_INTRO    = Decimal('0.02')    # 2% — birinchi 30 kun
PARK_COMMISSION_REGULAR  = Decimal('0.015')   # 1.5% — 30 kundan keyin
PARK_INTRO_DAYS          = 30                 # Kirish davri (kun)


def get_driver_commission_rate(driver) -> Decimal:
    """
    Haydovchiga qo'llaniladigan joriy komissiya stavkasini hisoblash.

    Park haydovchilariga YANGI qoida:
      - Birinchi 30 kun: 2%
      - 30 kundan keyin: 1.5%

    Solo haydovchilarga ESKI qoida (ustuvorlik tartibi):
      1. Kirish davri (intro) — 20%/19%
      2. Ertalabki soatlar (happy hours) — 16%/15%
      3. Maqsad chegirmasi (goal discount) — asosiy stavkadan chegirma
      4. Oddiy stavka (settings dan)
    """
    now = timezone.now()
    car_class = getattr(getattr(driver, 'vehicle', None), 'car_class', 'economy')
    is_electro = car_class == 'electro'

    # ── PARK HAYDOVCHISI: soddalashtirilgan 30-kun qoidasi ──────────────────
    if driver.taxi_park_id:
        join_date = driver.intro_period_start or driver.created_at
        if join_date:
            days_since = (now - join_date).days
            if days_since < PARK_INTRO_DAYS:
                return PARK_COMMISSION_INTRO     # 2%
        return PARK_COMMISSION_REGULAR           # 1.5%

    # ── SOLO HAYDOVCHI: eski murakkab qoida ────────────────────────────────
    # 1. Kirish davri tekshiruvi
    if not driver.intro_period_completed:
        completed_rides = driver.total_rides_completed or 0
        intro_start = driver.intro_period_start or driver.created_at

        hours_since = (now - intro_start).total_seconds() / 3600

        # Kirish davri tugash sharti: 15 ta YOKI (48 soat VA 8 ta)
        intro_done = (
            completed_rides >= INTRO_MAX_RIDES or
            (hours_since >= INTRO_HOURS and completed_rides >= INTRO_MIN_RIDES)
        )

        if not intro_done:
            return INTRO_COMMISSION_ELECTRO if is_electro else INTRO_COMMISSION_DEFAULT

        # Kirish davri tugadi — belgilaymiz
        driver.intro_period_completed = True
        driver.save(update_fields=['intro_period_completed'])

    # 2. Ertalabki soatlar: 07:00–09:00
    local_time = timezone.localtime(now)
    time_str = local_time.strftime('%H:%M')
    for hh in getattr(settings, 'HAPPY_HOURS', []):
        if hh['start'] <= time_str < hh['end']:
            return HAPPY_COMMISSION_ELECTRO if is_electro else HAPPY_COMMISSION_DEFAULT

    # 3. Maqsad chegirmasi
    base_rate = Decimal(str(settings.PRICING.get('COMMISSION_RATE', 0.05)))
    if driver.commission_discount_until and driver.commission_discount_rate > 0:
        if now.date() <= driver.commission_discount_until:
            discount = Decimal(str(driver.commission_discount_rate)) / Decimal('100')
            base_rate = max(Decimal('0.01'), base_rate - discount)

    return base_rate


# ---------------------------------------------------------------------------
# Haydovchi maqsad tizimi
# ---------------------------------------------------------------------------

def check_and_complete_driver_goal(driver, ride):
    """
    Har safar yakunlanganda haydovchining faol maqsadini tekshirish.
    Bajarilsa — mukofot berish va komissiya chegirmasini faollashtirish.
    """
    from accounts.models import GoalProgress, Wallet

    active_goal = GoalProgress.objects.filter(
        driver=driver, status='active'
    ).select_related('goal').first()

    if not active_goal:
        return

    today = timezone.now().date()

    # Muddat o'tganmi?
    if today > active_goal.end_date:
        active_goal.status = 'failed'
        active_goal.save(update_fields=['status'])
        logger.info("Maqsad muddati o'tdi: %s — %s", driver.user.phone, active_goal.goal.title)
        return

    active_goal.current_count += 1
    active_goal.save(update_fields=['current_count'])

    # Maqsad bajarildi?
    if active_goal.current_count >= active_goal.goal.min_rides and not active_goal.reward_paid:
        _award_goal_bonus(driver, active_goal)


def _award_goal_bonus(driver, goal_progress):
    """Maqsad bonusini haydovchiga berish."""
    from accounts.models import Wallet
    from datetime import timedelta

    goal = goal_progress.goal
    wallet, _ = Wallet.objects.get_or_create(user=driver.user)

    # Pul mukofoti
    wallet.deposit(
        goal.bonus_amount,
        f"Maqsad mukofoti: {goal.title} ({goal.min_rides} buyurtma)"
    )

    # Qo'shimcha 10 buyurtma — bu flagni saqlash (frontend ko'rsatadi)
    # TODO: extra_orders_bonus ni tracking qilish kerak

    # Komissiya chegirmasi: keyingi N kun
    today = timezone.now().date()
    driver.commission_discount_until = today + timedelta(days=goal.commission_discount_days)
    driver.commission_discount_rate = goal.commission_discount_percent
    driver.save(update_fields=['commission_discount_until', 'commission_discount_rate'])

    goal_progress.status = 'completed'
    goal_progress.reward_paid = True
    goal_progress.save(update_fields=['status', 'reward_paid'])

    logger.info(
        "Maqsad bajarildi: %s — %s | Mukofot: %s UZS | Chegirma: %s%% (%d kun)",
        driver.user.phone, goal.title, goal.bonus_amount,
        goal.commission_discount_percent, goal.commission_discount_days
    )
