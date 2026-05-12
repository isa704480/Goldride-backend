import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class BaseSMSProvider:
    def send_sms(self, phone: str, message: str) -> bool:
        raise NotImplementedError()

class SimulationProvider(BaseSMSProvider):
    def send_sms(self, phone: str, message: str) -> bool:
        logger.info(f" [SMS SIMULATION] To: {phone} | Message: {message}")
        print(f"\n--- SMS SIMULATION ---\nTo: {phone}\nMessage: {message}\n----------------------\n")
        return True

class EskizProvider(BaseSMSProvider):
    """Eskiz.uz API implementation"""
    BASE_URL = "https://notify.eskiz.uz/api"

    def _get_token(self):
        token = cache.get(settings.ESKIZ_TOKEN_CACHE_KEY)
        if token:
            return token

        try:
            resp = requests.post(f"{self.BASE_URL}/auth/login", data={
                'email': settings.ESKIZ_EMAIL,
                'password': settings.ESKIZ_PASSWORD
            })
            if resp.status_code == 200:
                token = resp.json().get('data', {}).get('token')
                # Cache for 23 hours (Eskiz tokens usually last 24h)
                cache.set(settings.ESKIZ_TOKEN_CACHE_KEY, token, 23 * 3600)
                return token
        except Exception as e:
            logger.error(f"Eskiz login error: {e}")
        return None

    def send_sms(self, phone: str, message: str) -> bool:
        token = self._get_token()
        if not token:
            logger.error("Failed to get Eskiz token")
            return False

        # Clean phone number (remove +)
        clean_phone = phone.replace('+', '').replace(' ', '')
        
        try:
            resp = requests.post(
                f"{self.BASE_URL}/message/sms/send",
                headers={'Authorization': f"Bearer {token}"},
                data={
                    'mobile_phone': clean_phone,
                    'message': message,
                    'from': '4546', # Default Eskiz nickname
                }
            )
            if resp.status_code == 200:
                logger.info(f"SMS sent to {phone} via Eskiz")
                return True
            else:
                logger.error(f"Eskiz send error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Eskiz API error: {e}")
        
        return False

class TelegramProvider(BaseSMSProvider):
    """Sends OTP via Telegram Bot API"""
    def send_sms(self, phone: str, message: str) -> bool:
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        chat_id = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '') # For demo, sending to admin or a log channel
        if not token or not chat_id:
            logger.error("Telegram token or chat_id not set")
            return SimulationProvider().send_sms(phone, message)

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, data={
                'chat_id': chat_id,
                'text': f"📲 Yangi OTP ({phone}):\n\n{message}"
            })
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram API error: {e}")
            return False

class EmailProvider(BaseSMSProvider):
    """Sends OTP via Email (Gmail/SMTP)"""
    def send_sms(self, phone: str, message: str) -> bool:
        from django.core.mail import send_mail
        # In this context, 'phone' is the email address identifier
        target_email = phone 
        try:
            send_mail(
                'Goldride Tasdiqlash Kodi',
                message,
                settings.DEFAULT_FROM_EMAIL,
                [target_email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

def get_otp_provider():
    provider_type = getattr(settings, 'OTP_PROVIDER', 'simulation')
    if provider_type == 'eskiz':
        return EskizProvider()
    elif provider_type == 'telegram':
        return TelegramProvider()
    elif provider_type == 'email':
        return EmailProvider()
    return SimulationProvider()
