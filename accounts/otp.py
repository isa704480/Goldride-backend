import logging
import random
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('accounts')


def _security_cfg():
    return getattr(settings, 'OTP_SECURITY', {
        'MAX_VERIFY_ATTEMPTS': 5,
        'BLOCK_DURATION_SECONDS': 900,
        'RESEND_COOLDOWN_SECONDS': 60,
        'MAX_SENDS_PER_HOUR': 5,
    })


def generate_otp(length=None):
    """Tasodifiy raqamli OTP kodi yaratish."""
    if length is None:
        length = settings.OTP_LENGTH
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])


def store_otp(phone: str, otp: str) -> None:
    """OTP ni keshda saqlash."""
    cache.set(f"otp:{phone}", otp, settings.OTP_EXPIRY_SECONDS)


def is_blocked(phone: str) -> int:
    """
    Agar foydalanuvchi bloklangan bo'lsa, qolgan sekundlarni qaytarish.
    Bloklangan bo'lmasa — 0.
    """
    ttl = cache.ttl(f"otp_block:{phone}")
    return ttl if ttl and ttl > 0 else 0


def can_send_otp(phone: str) -> tuple[bool, str]:
    """
    OTP yuborishdan oldin tekshiruv:
    - 15 daqiqalik bloklash aktiv emasmi?
    - So'nggi yuborishdan 60 soniya o'tdimi?
    - Bir soatda 5 martadan ko'p yuborilmadimi?

    Qaytarish: (ruxsat_bor, xato_xabari)
    """
    cfg = _security_cfg()

    # 1. Bloklash tekshiruvi
    block_ttl = is_blocked(phone)
    if block_ttl > 0:
        mins = block_ttl // 60
        secs = block_ttl % 60
        return False, f"Akkaunt {mins}:{secs:02d} daqiqa bloklangan."

    # 2. Qayta yuborish orasidagi minimal vaqt
    cooldown_key = f"otp_cooldown:{phone}"
    if cache.get(cooldown_key):
        return False, f"Kodni qayta yuborish uchun {cfg['RESEND_COOLDOWN_SECONDS']} soniya kutish kerak."

    # 3. Soatlik limit
    hourly_key = f"otp_hourly:{phone}"
    sends = cache.get(hourly_key, 0)
    if sends >= cfg['MAX_SENDS_PER_HOUR']:
        return False, "Bir soatda juda ko'p urinish. Keyinroq qayta urinib ko'ring."

    return True, ""


def record_otp_sent(phone: str) -> None:
    """OTP yuborilganidan keyin limitlarni yangilash."""
    cfg = _security_cfg()

    # Cooldown o'rnatish
    cache.set(f"otp_cooldown:{phone}", True, cfg['RESEND_COOLDOWN_SECONDS'])

    # Soatlik hisoblagich
    hourly_key = f"otp_hourly:{phone}"
    cache.get_or_set(hourly_key, 0, 3600)
    cache.incr(hourly_key)

    # Yangi yuborishda avvalgi urinish hisoblagichini tozalash
    cache.delete(f"otp_attempts:{phone}")


def verify_otp(phone: str, otp: str) -> bool:
    """
    OTP ni tekshirish.
    - 5 marta noto'g'ri kiritilsa: 15 daqiqa bloklash
    - To'g'ri bo'lsa: keshdan o'chirish
    """
    cfg = _security_cfg()

    # Bloklash tekshiruvi
    if is_blocked(phone):
        logger.warning("Bloklangan raqamdan OTP urinish: %s", phone)
        return False

    key = f"otp:{phone}"
    attempts_key = f"otp_attempts:{phone}"

    attempts = cache.get(attempts_key, 0)

    # Maksimal urinishlar tugadi — bloklash
    if attempts >= cfg['MAX_VERIFY_ATTEMPTS']:
        cache.set(f"otp_block:{phone}", True, cfg['BLOCK_DURATION_SECONDS'])
        cache.delete(key)
        cache.delete(attempts_key)
        logger.warning(
            "OTP brute-force: %s — %d ta noto'g'ri urinishdan so'ng bloklandi",
            phone, attempts
        )
        return False

    stored_otp = cache.get(key)
    if stored_otp and stored_otp == otp:
        cache.delete(key)
        cache.delete(attempts_key)
        logger.info("OTP muvaffaqiyatli tasdiqlandi: %s", phone)
        return True

    # Noto'g'ri urinish — hisoblagichni oshirish
    new_attempts = attempts + 1
    cache.set(attempts_key, new_attempts, settings.OTP_EXPIRY_SECONDS)
    remaining = cfg['MAX_VERIFY_ATTEMPTS'] - new_attempts
    logger.info(
        "Noto'g'ri OTP: %s (%d/%d urinish, %d qoldi)",
        phone, new_attempts, cfg['MAX_VERIFY_ATTEMPTS'], max(0, remaining)
    )
    return False


def send_otp(phone: str) -> str:
    """OTP yaratish, saqlash va yuborish."""
    otp = generate_otp()
    store_otp(phone, otp)
    record_otp_sent(phone)

    from .sms import get_otp_provider
    provider = get_otp_provider()
    message = f"Goldride: Tasdiqlash kodingiz: {otp}"
    provider.send_sms(phone, message)

    return otp


def get_otp_ttl(phone: str) -> int:
    """OTP ning qolgan amal qilish vaqtini (soniya) qaytarish. Topilmasa — 0."""
    key = f"otp:{phone}"
    if cache.get(key) is not None:
        return settings.OTP_EXPIRY_SECONDS
    return 0
