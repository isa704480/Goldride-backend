import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import User

class Command(BaseCommand):
    help = 'Runs the Telegram Bot for user authentication and notifications'

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            self.stderr.write('TELEGRAM_BOT_TOKEN is not set in settings')
            return

        self.stdout.write('Bot is starting...')
        offset = 0
        
        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
                resp = requests.get(url).json()
                
                if not resp.get('ok'):
                    self.stderr.write(f"Error from Telegram: {resp}")
                    time.sleep(5)
                    continue
                
                for update in resp.get('result', []):
                    offset = update['update_id'] + 1
                    message = update.get('message')
                    if not message:
                        continue
                        
                    chat_id = message['chat']['id']
                    text = message.get('text', '')
                    contact = message.get('contact')
                    
                    if text == '/start':
                        self.send_welcome(token, chat_id)
                    elif contact:
                        self.handle_contact(token, chat_id, contact)
                    else:
                        # Help message
                        self.send_message(token, chat_id, "Iltimos, pastdagi tugmani bosib telefon raqamingizni yuboring.")
                        
            except Exception as e:
                self.stderr.write(f"Bot error: {e}")
                time.sleep(5)

    def send_message(self, token, chat_id, text, reply_markup=None):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        if reply_markup:
            import json
            data['reply_markup'] = json.dumps(reply_markup)
        requests.post(url, data=data)

    def send_welcome(self, token, chat_id):
        text = "Goldride botiga xush kelibsiz! 👋\n\nTizimda ro'yxatdan o'tish va Chat ID olish uchun telefon raqamingizni yuboring."
        reply_markup = {
            'keyboard': [[{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.send_message(token, chat_id, text, reply_markup)

    def handle_contact(self, token, chat_id, contact):
        phone = contact['phone_number']
        if not phone.startswith('+'):
            phone = '+' + phone
        
        user = User.objects.filter(phone=phone).first()
        if user:
            user.telegram_chat_id = str(chat_id)
            user.save()
            self.send_message(token, chat_id, f"✅ Akkauntingiz bog'landi!\n\nEndi mobil ilovaga o'ting, **Telegram** bo'limini tanlang va ushbu Chat ID'ni kiriting:\n\nChat ID: `{chat_id}`")
        else:
            self.send_message(token, chat_id, f"❌ Telefon raqamingiz ({phone}) topilmadi.\n\nIltimos, avval ilovada ro'yxatdan o'ting, keyin botga qaytib Chat ID oling.\n\nSizning Chat ID: `{chat_id}`")
