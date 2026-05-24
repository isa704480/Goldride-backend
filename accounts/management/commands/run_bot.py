import time
import random
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.cache import cache
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
                        self.send_message(token, chat_id, "Iltimos, pastdagi tugmani bosib telefon raqamingizni yuboring.")

            except Exception as e:
                self.stderr.write(f"Bot error: {e}")
                time.sleep(5)

    def send_message(self, token, chat_id, text, parse_mode=None, reply_markup=None):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            import json
            data['reply_markup'] = json.dumps(reply_markup)
        requests.post(url, data=data)

    def send_welcome(self, token, chat_id):
        text = (
            "🚕 Goldride botiga xush kelibsiz!\n\n"
            "Tizimga kirish uchun telefon raqamingizni yuboring — "
            "sizga 6 xonali tasdiqlash kodi yuboriladi."
        )
        reply_markup = {
            'keyboard': [[{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]],
            'resize_keyboard': True,
            'one_time_keyboard': True
        }
        self.send_message(token, chat_id, text, reply_markup=reply_markup)

    def handle_contact(self, token, chat_id, contact):
        phone = contact['phone_number']
        if not phone.startswith('+'):
            phone = '+' + phone

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Store OTP and chat_id in cache (5 minutes)
        cache.set(f'tg_otp:{phone}', otp, timeout=300)
        cache.set(f'tg_chat:{phone}', str(chat_id), timeout=300)

        user = User.objects.filter(phone=phone).first()
        if user:
            msg = (
                f"✅ Akkauntingiz topildi!\n\n"
                f"Ilovaga kirish uchun ushbu kodni kiriting:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa davomida amal qiladi."
            )
        else:
            msg = (
                f"📱 Telefon: {phone}\n\n"
                f"Ilovaga kirish uchun ushbu kodni kiriting:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa davomida amal qiladi.\n\n"
                f"❗ Agar akkauntingiz yo'q bo'lsa, avval ilovada ro'yxatdan o'ting."
            )

        self.send_message(token, chat_id, msg, parse_mode='HTML')
