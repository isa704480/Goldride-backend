"""
Goldride Telegram Bot.

Muammo hal qilindi:
  Oldin bot OTP ni memory cache'ga yozar, Daphne (veb-server) boshqa process bo'lgani uchun
  o'sha cache'ni ko'ra olmas edi. Endi TelegramOTP modeli (DB) ishlatiladi — ikki process ham
  bir xil bazani ko'radi.
"""

import time
import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger('accounts')


class Command(BaseCommand):
    help = 'Goldride Telegram Botini ishga tushirish'

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            self.stderr.write('TELEGRAM_BOT_TOKEN sozlanmagan')
            return

        self.token = token
        self.stdout.write('Bot ishga tushmoqda...')
        offset = 0

        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
                resp = requests.get(url, timeout=35).json()

                if not resp.get('ok'):
                    self.stderr.write(f"Telegram xatosi: {resp}")
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
                        self._send_welcome(chat_id)
                    elif contact:
                        self._handle_contact(chat_id, contact)
                    else:
                        self._send_message(
                            chat_id,
                            "Iltimos, pastdagi tugmani bosib telefon raqamingizni yuboring."
                        )

            except Exception as e:
                logger.error("Bot xatosi: %s", e)
                time.sleep(5)

    def _send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        import json
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        if parse_mode:
            data['parse_mode'] = parse_mode
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        try:
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            logger.error("Xabar yuborishda xatolik: %s", e)

    def _send_welcome(self, chat_id):
        text = (
            "🚕 <b>Goldride</b> botiga xush kelibsiz!\n\n"
            "📱 Tizimga kirish uchun telefon raqamingizni yuboring.\n"
            "Sizga 6 xonali tasdiqlash kodi yuboriladi."
        )
        reply_markup = {
            'keyboard': [[{
                'text': '📱 Telefon raqamni yuborish',
                'request_contact': True,
            }]],
            'resize_keyboard': True,
            'one_time_keyboard': True,
        }
        self._send_message(chat_id, text, parse_mode='HTML', reply_markup=reply_markup)

    def _handle_contact(self, chat_id, contact):
        """
        Foydalanuvchi kontaktini yubordi — DB'ga OTP yozib, yuborish.
        TelegramOTP modeli ishlatiladi (cache emas!) — process izolyatsiyasi muammosi yo'q.
        """
        from accounts.models import User, TelegramOTP

        phone = contact.get('phone_number', '')
        if not phone.startswith('+'):
            phone = '+' + phone

        # DB'ga OTP yozish
        otp_entry = TelegramOTP.create_otp(phone, chat_id=chat_id)
        otp = otp_entry.otp

        user = User.objects.filter(phone=phone).first()
        if user:
            user.telegram_chat_id = str(chat_id)
            user.save(update_fields=['telegram_chat_id'])

        if user:
            msg = (
                f"✅ <b>Akkauntingiz topildi!</b>\n\n"
                f"Ilovaga kirish uchun ushbu kodni kiriting:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa davomida amal qiladi."
            )
        else:
            msg = (
                f"📱 Telefon: <code>{phone}</code>\n\n"
                f"Ilovaga kirish uchun ushbu kodni kiriting:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa davomida amal qiladi.\n\n"
                f"❗ Yangi foydalanuvchi — ilovada ro'yxatdan o'tishingiz kerak bo'ladi."
            )

        self._send_message(chat_id, msg, parse_mode='HTML')
        logger.info("Telegram OTP yuborildi: %s (chat_id: %s)", phone, chat_id)
