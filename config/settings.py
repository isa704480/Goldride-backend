import os
import logging
from pathlib import Path
from datetime import timedelta
from decouple import config
import dj_database_url

# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration

BASE_DIR = Path(__file__).resolve().parent.parent

# Sentry Monitoring
# SENTRY_DSN = config('SENTRY_DSN', default='')
# if SENTRY_DSN:
#     sentry_sdk.init(
#         dsn=SENTRY_DSN,
#         integrations=[DjangoIntegration()],
#         traces_sample_rate=1.0,
#         send_default_pii=True
#     )

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key')
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')
ALLOWED_HOSTS.append('goldride-backend-production.up.railway.app')
ALLOWED_HOSTS.append('goldride-admin.vercel.app')
if config('RAILWAY_STATIC_URL', default=''):
    ALLOWED_HOSTS.append(config('RAILWAY_STATIC_URL'))
if config('RAILWAY_PUBLIC_DOMAIN', default=''):
    ALLOWED_HOSTS.append(config('RAILWAY_PUBLIC_DOMAIN'))

CSRF_TRUSTED_ORIGINS = [
    'https://' + host for host in ALLOWED_HOSTS if host != '*'
]
CSRF_TRUSTED_ORIGINS.append('http://localhost:8081') # For Expo dev
CSRF_TRUSTED_ORIGINS.append('https://goldride-admin.vercel.app')
CSRF_TRUSTED_ORIGINS.append('https://goldride-reklama.vercel.app')


# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'channels',
    # Local apps
    'accounts',
    'rides',
    'pricing',
    'matching',
    'realtime',
    'drf_yasg',
]

MIDDLEWARE = [
    # DebugMiddleware OLIB TASHLANDI: u har bir javobga 'Access-Control-Allow-Origin: *'
    # qo'yib, production'da CORS cheklovlarini bekor qilardi. CORS'ni faqat
    # corsheaders boshqaradi (quyidagi CORS_ALLOWED_ORIGINS bo'yicha).
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database — SQLite for dev, PostgreSQL for production
USE_POSTGRES = config('USE_POSTGRES', default=False, cast=bool)
DATABASE_URL = config('DATABASE_URL', default='')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=600)
    }
elif USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='taksi_db'),
            'USER': config('DB_USER', default='taksi_user'),
            'PASSWORD': config('DB_PASSWORD', default='taksi_pass_2026'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Cache — Redis for production, local memory for dev
USE_REDIS = config('USE_REDIS', default=False, cast=bool)

if USE_REDIS:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('CACHE_REDIS_URL', default='redis://localhost:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [config('REDIS_URL', default='redis://localhost:6379/0')],
            },
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'estimate_price': '20/min',
        'auth_limit': '5/min',
    }
}


# JWT Settings
SIMPLE_JWT = {
    # Access token qisqa muddatli — o'g'irlansa zarar kam (avval 12 soat edi)
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Railway HTTPS fix
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Production xavfsizlik flaglari (faqat DEBUG=False bo'lganda)
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 yil
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Firebase (Google bilan kirish) — service account JSON fayl yo'li
FIREBASE_CREDENTIALS_FILE = config('FIREBASE_CREDENTIALS_FILE', default='')

# CORS — production'da faqat ruxsat berilgan domenlar
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = [
        'https://goldride.uz',
        'https://www.goldride.uz',
        'https://park.goldride.uz',
        'https://admin.goldride.uz',
        'https://goldride-admin.vercel.app',
        'https://goldride-reklama.vercel.app',
        'https://goldride-taxipark.vercel.app',
        'http://localhost:8081',
        'http://localhost:3000',
        'http://localhost:5173',
    ]
    # Qo'shimcha domenlarni .env orqali kiritish mumkin (vergul bilan)
    _extra_cors = config('CORS_EXTRA_ORIGINS', default='')
    if _extra_cors:
        CORS_ALLOWED_ORIGINS += [o.strip() for o in _extra_cors.split(',') if o.strip()]
CORS_ALLOW_CREDENTIALS = False

# OTP Settings
OTP_EXPIRY_SECONDS = config('OTP_EXPIRY_SECONDS', default=300, cast=int)
OTP_LENGTH = config('OTP_LENGTH', default=4, cast=int)

# OTP — Google (Firebase) asosiy, SMS o'chirildi
# OTP_PROVIDER = config('OTP_PROVIDER', default='simulation')

# Telegram OTP
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_ADMIN_CHAT_ID = config('TELEGRAM_ADMIN_CHAT_ID', default='')
# Webhook URL: Railway deployment manzili (masalan: https://goldride-backend-production.up.railway.app)
# Bot polling EMAS, webhook ishlatiladi — bir nechta instance muammosi yo'q
TELEGRAM_WEBHOOK_BASE_URL = config('TELEGRAM_WEBHOOK_BASE_URL', default='')

# Reklama saytidagi "Fikringiz" formasi uchun alohida bot (vergul bilan ajratilgan chat_id'lar)
# Default qiymatlar production'da (Railway) env o'zgaruvchisi qo'yilmagan holda ham
# ishlashi uchun berilgan. Railway Variables'da FEEDBACK_BOT_TOKEN qo'ysangiz, u ustun turadi.
# Eslatma: bu send-only bot faqat quyidagi chat'larga xabar yuboradi.
FEEDBACK_BOT_TOKEN = config('FEEDBACK_BOT_TOKEN', default='8847199657:AAGhvkU9cO6ULkrx6ps1KGnPG4NhPPQKy-k')
FEEDBACK_CHAT_IDS = config('FEEDBACK_CHAT_IDS', default='8706124108,6102501581')

# Email OTP (Gmail/SMTP)
OTP_EMAIL_RECIPIENT = config('OTP_EMAIL_RECIPIENT', default='admin@goldride.uz')
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# Pricing Settings (UZS)
PRICING = {
    'BASE_FARE': config('BASE_FARE', default=5000, cast=int),
    'PER_KM_RATE': config('PER_KM_RATE', default=2000, cast=int),
    'SHARED_DISCOUNT': config('SHARED_DISCOUNT', default=0.30, cast=float),
    'COMMISSION_RATE': config('COMMISSION_RATE', default=0.05, cast=float),
    'MIN_FARE': 3000,
    'MAX_PASSENGERS_PER_RIDE': 2,
}

# Matching Settings
MATCHING = {
    'SEARCH_RADIUS_KM': 5,
    'MAX_ROUTE_DEVIATION': 0.20,
    'MATCH_TIME_WINDOW_MINUTES': 5,
    'DRIVER_LOCATION_UPDATE_INTERVAL': 3,
}

# Happy Hours — faqat ertalab 07:00–09:00 (16%/15% komissiya)
HAPPY_HOURS = [
    {'start': '07:00', 'end': '09:00', 'commission_rate': 0.16, 'label': 'Ertalabki soatlar'},
]

# Haydovchi minimal balans va bonus sozlamalari (UZS)
DRIVER_BALANCE = {
    'FIRST_MONTH_MINIMUM': 10000,   # 1-oy ichida minimal balans
    'AFTER_MONTH_MINIMUM': 20000,   # 2+ oydan keyingi minimal balans
    'SIGNUP_BONUS': 10000,          # Yangi haydovchiga beriladigan kirish bonusi
    'FIRST_MONTH_DAYS': 30,         # 1-oy davomiyligi (kunlarda)
    'MAX_CONCURRENT_RIDES': 3,      # Bir vaqtda maksimal faol buyurtmalar soni
}

# Yo'lovchi bekor qilish jarimasi
CANCELLATION_POLICY = {
    'MAX_CANCELLATIONS': 3,         # Maksimal ketma-ket bekor qilish
    'TIME_WINDOW_HOURS': 1,         # Sanash uchun vaqt oynasi (soat)
    'PENALTY_STEP_1': 1000,         # 1-bekor qilish jarimasi
    'PENALTY_STEP_2': 2000,         # 2-bekor qilish jarimasi
    'PENALTY_BLOCK': 5000,          # 3-va undan keyingi jarima (bloklashdan oldin)
}

# Geo-fencing: Faqat Toshkent ichida ishlash uchun
TASHKENT_BOUNDARY = {
    'LAT_MIN': 41.15,
    'LAT_MAX': 41.45,
    'LNG_MIN': 69.05,
    'LNG_MAX': 69.50,
}

# OTP brute-force himoya sozlamalari
OTP_SECURITY = {
    'MAX_VERIFY_ATTEMPTS': 5,       # Maksimal noto'g'ri urinishlar soni
    'BLOCK_DURATION_SECONDS': 900,  # Bloklash muddati: 15 daqiqa
    'RESEND_COOLDOWN_SECONDS': 60,  # Qayta yuborish orasidagi minimal vaqt
    'MAX_SENDS_PER_HOUR': 5,        # Bir soatda maksimal yuborish soni
}

# Logging sozlamalari
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',  # stderr emas stdout — terminalda qizil chiqmasin
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'matching': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'rides': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'pricing': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Swagger / drf_yasg sozlamalari
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT token: **Bearer &lt;token&gt;**',
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'SUPPORTED_SUBMIT_METHODS': ['get', 'post', 'put', 'patch', 'delete'],
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DOC_EXPANSION': 'none',   # Hammasi yopiq holda ochiladi
    'DEFAULT_MODEL_RENDERING': 'example',
    'DEEP_LINKING': True,
    'SHOW_EXTENSIONS': False,
    'SHOW_COMMON_EXTENSIONS': False,
    'PERSIST_AUTH': True,      # Token kiritilgandan keyin saqlanib qoladi
}

REDOC_SETTINGS = {
    'LAZY_RENDERING': True,
    'HIDE_HOSTNAME': False,
    'EXPAND_RESPONSES': 'none',
    'PATH_IN_MIDDLE': False,
}
