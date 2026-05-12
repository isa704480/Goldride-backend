import os
import sys
import django

# Add backend root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.conf import settings
from django.core.mail import send_mail

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def test_email():
    print("Testing email sending...")
    try:
        send_mail(
            'Goldride SMTP Test',
            'Bu SMTP test xabari.',
            settings.DEFAULT_FROM_EMAIL,
            ['mansurovislombek130@gmail.com'], # Sending to self for test
            fail_silently=False,
        )
        print("SUCCESS: Email sent successfully!")
    except Exception as e:
        print(f"FAILED: Email error: {e}")

if __name__ == "__main__":
    test_email()
