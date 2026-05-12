import random
from django.conf import settings
from django.core.cache import cache



def generate_otp(length=None):
    """Generate a random numeric OTP code."""
    if length is None:
        length = settings.OTP_LENGTH
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])


def store_otp(phone: str, otp: str) -> None:
    """Store OTP in cache with expiry."""
    key = f"otp:{phone}"
    cache.set(key, otp, settings.OTP_EXPIRY_SECONDS)


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP from cache with rate limiting."""
    key = f"otp:{phone}"
    attempts_key = f"otp_attempts:{phone}"
    
    attempts = cache.get(attempts_key, 0)
    if attempts >= 5:
        cache.delete(key)
        return False
        
    stored_otp = cache.get(key)
    if stored_otp and stored_otp == otp:
        cache.delete(key)
        cache.delete(attempts_key)
        return True
        
    # Increment failed attempts
    cache.set(attempts_key, attempts + 1, settings.OTP_EXPIRY_SECONDS)
    return False


def send_otp(phone: str) -> str:
    """
    Generate OTP, store in cache, and send via SMS.
    """
    otp = generate_otp()
    store_otp(phone, otp)
    
    # Reset attempts on new OTP request
    cache.delete(f"otp_attempts:{phone}")
    
    # Send OTP via selected provider (SMS/Telegram/Email)
    from .sms import get_otp_provider
    provider = get_otp_provider()
    message = f"Goldride: Tasdiqlash kodingiz: {otp}"
    provider.send_sms(phone, message)
    
    return otp


def get_otp_ttl(phone: str) -> int:
    """Get remaining TTL for an OTP. Returns 0 if not found."""
    key = f"otp:{phone}"
    # Django cache doesn't expose TTL directly
    # Check if key exists
    if cache.get(key) is not None:
        return settings.OTP_EXPIRY_SECONDS  # Approximate
    return 0
