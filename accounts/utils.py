import logging
import requests
from django.conf import settings

logger = logging.getLogger('accounts')

# Firebase Admin SDK lazy-init holati
_firebase_app = None
_firebase_init_failed = False


def _get_firebase_app():
    """Firebase Admin ilovasini bir marta ishga tushirish (lazy)."""
    global _firebase_app, _firebase_init_failed
    if _firebase_app is not None:
        return _firebase_app
    if _firebase_init_failed:
        return None

    cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_FILE', '')
    if not cred_path:
        _firebase_init_failed = True
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception as e:
        logger.error("Firebase Admin init xatosi: %s", e)
        _firebase_init_failed = True
        return None


def verify_firebase_id_token(id_token):
    """
    Firebase ID tokenni tekshirish.

    Firebase sozlanmagan bo'lsa, Google tokeninfo API dan foydalaniladi (fallback).

    Qaytaradi: (decoded_dict, error)
      - (payload, None)           — token to'g'ri
      - (None, 'not_configured')  — hech qaysi usul sozlanmagan
      - (None, 'invalid')         — token yaroqsiz
    """
    app = _get_firebase_app()

    if app is not None:
        # Firebase Admin SDK orqali tekshirish
        try:
            from firebase_admin import auth as fb_auth
            decoded = fb_auth.verify_id_token(id_token, app=app)
            return decoded, None
        except Exception as e:
            logger.warning("Firebase token tekshiruvi muvaffaqiyatsiz: %s", e)
            return None, 'invalid'

    # Firebase sozlanmagan — Google tokeninfo API orqali tekshirish (fallback)
    logger.info("Firebase sozlanmagan. Google tokeninfo API ishlatilmoqda.")
    try:
        resp = requests.get(
            'https://oauth2.googleapis.com/tokeninfo',
            params={'id_token': id_token},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            email_verified = data.get('email_verified')
            if email_verified in (True, 'true', '1'):
                return data, None
            logger.warning("Google tokeninfo: email tasdiqlanmagan: %s", data.get('email'))
            return None, 'invalid'

        logger.warning("Google tokeninfo API xatosi: %s — %s", resp.status_code, resp.text[:200])
        return None, 'invalid'
    except Exception as e:
        logger.warning("Google tokeninfo so'rov xatosi: %s", e)
        return None, 'invalid'


def send_telegram_notification(message, chat_id=None):
    """Sends a notification message to the configured Telegram bot/chat or specific chat_id."""
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    
    if not chat_id:
        chat_id = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', None)
    
    if not token or not chat_id:
        print("[Telegram] Missing token or chat_id")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            print(f"[Telegram] Error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error sending message: {e}")
        return False
