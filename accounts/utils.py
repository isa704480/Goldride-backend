import requests
from django.conf import settings

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
