import os
import django
from django.core.mail import send_mail

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def test_email():
    try:
        send_mail(
            'Goldride Test',
            'Sizning SMTP tizimingiz muvaffaqiyatli ishga tushdi!',
            'mansurovislombek130@gmail.com',
            ['mansurovislombek130@gmail.com'],
            fail_silently=False,
        )
        print("Email muvaffaqiyatli yuborildi!")
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    test_email()
