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


def get_otp_provider():
    """Faqat SimulationProvider — SMS va OTP o'chirildi."""
    return SimulationProvider()
