import logging
from django.utils import timezone
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from decimal import Decimal
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Driver, SavedLocation, User
from .otp import send_otp, verify_otp, get_otp_ttl, can_send_otp
from .serializers import (
    SendOTPSerializer,
    VerifyOTPSerializer,
    UserRegistrationSerializer,
    UserProfileSerializer,
    DriverRegistrationSerializer,
    DriverProfileSerializer,
    DriverLocationSerializer,
    SavedLocationSerializer,
    WalletSerializer,
    WalletRequestSerializer,
    DriverPublicRegistrationSerializer,
)
from .utils import send_telegram_notification
from django.conf import settings

logger = logging.getLogger('accounts')
User = get_user_model()


@swagger_auto_schema(
    method='post',
    tags=['Auth'],
    operation_summary='OTP yuborish',
    operation_description='Telefon raqam yoki emailga OTP kodi yuboradi.',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'phone': openapi.Schema(type=openapi.TYPE_STRING, example='+998901234567'),
            'email': openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
        },
    ),
    responses={
        200: openapi.Response('OTP yuborildi', openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'detail': openapi.Schema(type=openapi.TYPE_STRING)},
        )),
        429: 'Juda ko\'p urinish',
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp_view(request):
    """OTP yuborish — telefon yoki email."""
    phone = request.data.get('phone')
    email = request.data.get('email')

    if not phone and not email:
        return Response({'detail': 'Telefon raqami yoki email kiritish shart.'}, status=400)

    identifier = email if email else phone

    # Brute-force va rate-limit tekshiruvi
    allowed, reason = can_send_otp(identifier)
    if not allowed:
        logger.warning("OTP yuborishda rad etildi: %s — %s", identifier, reason)
        return Response({'detail': reason}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    # Generate and store OTP
    from .otp import generate_otp, store_otp
    otp = generate_otp()
    store_otp(identifier, otp)
    
    # If phone is also provided, store it in cache linked to this identifier
    if phone and email:
        from django.core.cache import cache
        cache.set(f"otp_phone:{identifier}", phone, 600) # 10 mins

    from .sms import get_otp_provider
    if email:
        # Explicitly use Email Provider
        from .sms import EmailProvider
        provider = EmailProvider()
        message = f"Goldride: Tasdiqlash kodingiz: {otp}"
        provider.send_sms(email, message)
    else:
        provider = get_otp_provider()
        message = f"Goldride: Tasdiqlash kodingiz: {otp}"
        provider.send_sms(phone, message)

    response_data = {
        'detail': f'Kod {email if email else phone} manziliga yuborildi.',
        'expires_in': 300,
    }

    if settings.DEBUG:
        response_data['otp'] = otp

    return Response(response_data, status=status.HTTP_200_OK)


def is_name_weird(name):
    """Checks if a name looks like a placeholder or has weird characters."""
    if not name or len(name) < 2:
        return True
    # If name has too many non-alphabetical characters
    import re
    if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\']+$', name):
        return True
    return False

@swagger_auto_schema(
    method='post',
    tags=['Auth'],
    operation_summary='OTP tasdiqlash → JWT token',
    operation_description=(
        'OTP kodni tasdiqlaydi. Agar foydalanuvchi yangi bo\'lsa `status: partial` qaytaradi '
        '(qo\'shimcha ma\'lumot kerak). Muvaffaqiyatli bo\'lsa `access` va `refresh` token qaytaradi.'
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['otp'],
        properties={
            'phone':      openapi.Schema(type=openapi.TYPE_STRING, example='+998901234567'),
            'email':      openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
            'otp':        openapi.Schema(type=openapi.TYPE_STRING, example='1234'),
            'first_name': openapi.Schema(type=openapi.TYPE_STRING, example='Ali'),
            'last_name':  openapi.Schema(type=openapi.TYPE_STRING, example='Valiyev'),
            'tg_login':   openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Telegram orqali kirish'),
        },
    ),
    responses={
        200: openapi.Response('Kirish muvaffaqiyatli', openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'access':  openapi.Schema(type=openapi.TYPE_STRING),
                'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                'status':  openapi.Schema(type=openapi.TYPE_STRING, example='ok'),
            },
        )),
        400: 'Noto\'g\'ri kod',
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_view(request):
    """
    Smart Verification:
    1. Verifies Code.
    2. Checks for existing user.
    3. If new/incomplete, returns next_steps (phone, name, etc.)
    """
    phone = request.data.get('phone')
    email = request.data.get('email')
    tg_username = request.data.get('telegram_username')
    otp = request.data.get('otp')
    tg_login = request.data.get('tg_login', False)

    # --- TELEGRAM 6 xonali OTP flow ---
    if tg_login and phone and otp:
        from accounts.models import TelegramOTP
        if not phone.startswith('+'): phone = '+' + phone

        # DB dan tekshirish (cache emas — process izolyatsiyasi muammosi yo'q)
        otp_entry = TelegramOTP.verify(phone, str(otp))
        if not otp_entry:
            logger.warning("Telegram OTP xato: %s", phone)
            return Response({'detail': 'Kod noto\'g\'ri yoki muddati o\'tgan.'}, status=400)

        chat_id = otp_entry.chat_id

        user = User.objects.filter(phone=phone).first()
        device_id = request.data.get('device_id')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

        if user:
            if chat_id:
                user.telegram_chat_id = chat_id
            user.device_id = device_id
            user.last_ip = ip
            user.save(update_fields=['telegram_chat_id', 'device_id', 'last_ip'])
            if user.is_blocked:
                return Response({'detail': 'Sizning akkauntingiz bloklangan.'}, status=403)
            refresh = RefreshToken.for_user(user)
            return Response({
                'status': 'ok',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserProfileSerializer(user).data,
            })

        # New user via Telegram — ask for name
        return Response({
            'detail': 'Profilni yakunlash kerak.',
            'status': 'partial',
            'missing_fields': ['first_name', 'last_name'],
            'prefill': {'phone': phone}
        }, status=200)

    identifier = email if email else (phone or tg_username)

    if not identifier or not otp:
        return Response({'detail': 'Ma\'lumotlar yetarli emas.'}, status=400)

    if not verify_otp(identifier, otp):
        return Response({'detail': 'Noto\'g\'ri yoki muddati o\'tgan kod.'}, status=400)

    # If email was used for OTP, check if we had a linked phone
    if email and not phone:
        from django.core.cache import cache
        phone = cache.get(f"otp_phone:{email}")

    # Find user
    user = None
    if phone:
        if not phone.startswith('+'): phone = '+' + phone
        user = User.objects.filter(phone=phone).first()
    elif email:
        user = User.objects.filter(email=email).first()
    elif tg_username:
        user = User.objects.filter(telegram_chat_id=str(tg_username)).first()
    
    # --- ANTI-FRAUD CHECK ---
    device_id = request.data.get('device_id')
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    # If user exists, update device/IP and log in
    if user:
        user.device_id = device_id
        user.last_ip = ip
        if email and not user.email:
            user.email = email
        user.save(update_fields=['device_id', 'last_ip', 'email'])
        
        if user.is_blocked:
            return Response({'detail': 'Sizning akkauntingiz bloklangan.'}, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            'status': 'ok',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data
        })

    # If new user, we need to gather data
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')
    
    # Determine what's missing
    missing_fields = []
    if not phone:
        missing_fields.append('phone')
    if is_name_weird(first_name):
        missing_fields.append('first_name')
    if is_name_weird(last_name):
        missing_fields.append('last_name')

    if missing_fields:
        return Response({
            'detail': 'Profilni yakunlash kerak.',
            'status': 'partial',
            'missing_fields': missing_fields,
            'prefill': {
                'phone': phone,
                'email': email,
                'first_name': first_name,
                'last_name': last_name
            }
        }, status=200)

    # If all fields present
    referral_code = request.data.get('referral_code')
    user, created = User.objects.get_or_create(
        phone=phone,
        defaults={
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'username': phone,
            'device_id': device_id,
            'last_ip': ip,
            'is_verified': True
        }
    )

    if created and referral_code:
        # Award bonus to the NEW user for using a referral code
        # (The inviter's bonus is handled per-ride, but we can also log it here)
        if user.bonus_balance is None:
            user.bonus_balance = Decimal('0')
        user.bonus_balance += Decimal('10000')
        user.save(update_fields=['bonus_balance'])
        
        # Link to the referrer for future per-ride bonuses
        from accounts.models import User as UserAccount
        referrer = UserAccount.objects.filter(referral_code=referral_code).first()
        if referrer:
            user.referred_by = referrer
            user.save(update_fields=['referred_by'])
    
    refresh = RefreshToken.for_user(user)
    return Response({
        'status': 'ok',
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'is_new_user': created,
        'user': UserProfileSerializer(user).data
    })


@swagger_auto_schema(
    method='post',
    tags=['Auth'],
    operation_summary='Admin login (phone + parol)',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['phone', 'password'],
        properties={
            'phone':    openapi.Schema(type=openapi.TYPE_STRING, example='+998901234567'),
            'password': openapi.Schema(type=openapi.TYPE_STRING, example='••••••••'),
        },
    ),
    responses={200: 'JWT token', 401: 'Noto\'g\'ri ma\'lumotlar'}
)
@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login_view(request):
    """Admin panel uchun phone + parol bilan kirish."""
    phone = request.data.get('phone')
    password = request.data.get('password')

    if not phone or not password:
        return Response({'error': 'Telefon va parolni kiriting'}, status=status.HTTP_400_BAD_REQUEST)

    logger.info("Admin login urinishi: %s", phone)
    
    from django.db.models import Q
    from django.contrib.auth import authenticate
    
    user_obj = User.objects.filter(Q(phone=phone) | Q(username=phone)).first()
    if not user_obj:
        return Response({'error': 'Foydalanuvchi topilmadi'}, status=status.HTTP_401_UNAUTHORIZED)
        
    user = authenticate(request, username=user_obj.username, password=password)
    
    if not user:
        return Response({'error': 'Noto\'g\'ri parol'}, status=status.HTTP_401_UNAUTHORIZED)

    if not (user.is_staff or user.is_superuser):
        return Response({'error': 'Kirishga ruxsat yo\'q'}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserProfileSerializer(user).data
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def login_direct_view(request):
    """Direct login/registration via phone number (skipping OTP)."""
    serializer = SendOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data['phone']

    if phone and not phone.startswith('+'):
        phone = '+' + phone

    # Get or create user
    ref_code = request.data.get('referral_code')
    user, created = User.objects.get_or_create(
        phone=phone,
        defaults={
            'username': phone, 
            'is_verified': True
        }
    )

    if created and ref_code:
        if user.bonus_balance is None:
            user.bonus_balance = Decimal('0')
        user.bonus_balance += Decimal('10000')
        user.save(update_fields=['bonus_balance'])
        
        referrer = User.objects.filter(referral_code=ref_code).first()
        if referrer:
            user.referred_by = referrer
            user.save(update_fields=['referred_by'])

    # Bonus logic moved to where profile is completed
    pass

    if created and ref_code:
        try:
            from rides.models import ReferralBonus
            referrer = User.objects.get(referral_code=ref_code)
            user.referred_by = referrer
            user.save()
            ReferralBonus.objects.create(user=referrer, referred_user=user, amount=10000, is_paid=True)
            referrer.add_gold_points(10)
            user.add_gold_points(5)
        except User.DoesNotExist:
            pass

    if not user.is_verified:
        user.is_verified = True
        user.save()

    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)

    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'is_new_user': created,
        'user': UserProfileSerializer(user).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_user_view(request):
    """Complete user registration with profile details."""
    serializer = UserRegistrationSerializer(
        instance=request.user,
        data=request.data,
        partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response(UserProfileSerializer(request.user).data)


class NearbyDriversView(generics.ListAPIView):
    """List online drivers for the live map."""
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # In a real app, we would filter by distance (lat/lng)
        # For now, return all online and approved drivers
        return Driver.objects.filter(is_online=True, status='approved').select_related('user', 'vehicle')


class UserProfileView(generics.RetrieveUpdateAPIView):
    """Get or update current user profile."""
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = self.get_object()
        # Check if first_name is being set for the first time
        is_first_completion = not user.first_name and serializer.validated_data.get('first_name')
        
        serializer.save()
        
        if is_first_completion:
            from django.conf import settings as conf_settings
            from accounts.models import Wallet
            # Get bonus amount from settings (default 20000)
            bonus_amount = 20000
            if hasattr(conf_settings, 'DRIVER_BALANCE'):
                bonus_amount = conf_settings.DRIVER_BALANCE.get('SIGNUP_BONUS', 20000)
                
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet.deposit(bonus_amount, "Xush kelibsiz bonusi")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_driver_view(request):
    """Register as a driver with vehicle details."""
    if hasattr(request.user, 'driver_profile'):
        return Response(
            {'detail': 'Siz allaqachon haydovchi sifatida ro\'yxatdan o\'tgansiz.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = DriverRegistrationSerializer(
        data=request.data,
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    driver = serializer.save()

    return Response(
        DriverProfileSerializer(driver).data,
        status=status.HTTP_201_CREATED
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def register_driver_public_view(request):
    """Register as a driver publicly from the website (landing page)."""
    serializer = DriverPublicRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    phone = serializer.validated_data['phone']
    first_name = serializer.validated_data['first_name']
    last_name = serializer.validated_data['last_name']
    license_number = serializer.validated_data['license_number']
    
    # Check if user already exists
    user, created = User.objects.get_or_create(
        phone=phone,
        defaults={
            'username': phone,
            'first_name': first_name,
            'last_name': last_name,
            'role': 'driver',
            'is_verified': True
        }
    )
    
    if not created:
        # If user exists, update their role and verification status
        user.role = 'driver'
        user.is_verified = True
        if not user.first_name:
            user.first_name = first_name
        if not user.last_name:
            user.last_name = last_name
        user.save()
        
    # Check if driver profile already exists
    if hasattr(user, 'driver_profile'):
        return Response(
            {'detail': 'Ushbu telefon raqami bilan haydovchi allaqachon ro\'yxatdan o\'tgan.'},
            status=status.HTTP_400_BAD_REQUEST
        )
        
    driver = Driver.objects.create(
        user=user,
        license_number=license_number,
        status='pending'  # pending, so it appears in the admin panel!
    )
    
    # Create the Vehicle
    from .models import Vehicle
    Vehicle.objects.create(
        driver=driver,
        make=serializer.validated_data['make'],
        model=serializer.validated_data['vehicle_model'],
        year=serializer.validated_data['year'],
        color=serializer.validated_data['color'],
        plate_number=serializer.validated_data['plate_number'],
        vehicle_type=serializer.validated_data.get('vehicle_type', 'sedan'),
    )
    
    # Create user Wallet (will be funded upon admin approval)
    from accounts.models import Wallet
    Wallet.objects.get_or_create(user=user)
    
    return Response(
        {'detail': 'Muvaffaqiyatli ro\'yxatdan o\'tdingiz. Tez orada admin tasdiqlaydi.'},
        status=status.HTTP_201_CREATED
    )


class DriverProfileView(generics.RetrieveUpdateAPIView):
    """Get or update driver profile."""
    serializer_class = DriverProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.driver_profile


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_driver_status(request):
    """Toggle driver online/offline status."""
    try:
        driver = request.user.driver_profile
    except Driver.DoesNotExist:
        return Response(
            {'detail': 'Haydovchi profili topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if driver.status != 'approved':
        return Response(
            {'detail': 'Sizning profilingiz hali tasdiqlanmagan.'},
            status=status.HTTP_403_FORBIDDEN
        )

    if not driver.is_online:
        # === Trying to go online — Minimal balans tekshiruvi ===
        from django.utils import timezone
        from django.conf import settings as conf_settings
        from datetime import timedelta

        balance_config = conf_settings.DRIVER_BALANCE
        days_since_signup = (timezone.now() - driver.created_at).days

        if days_since_signup <= balance_config['FIRST_MONTH_DAYS']:
            min_balance = balance_config['FIRST_MONTH_MINIMUM']
            month_label = "1-oy"
        else:
            min_balance = balance_config['AFTER_MONTH_MINIMUM']
            month_label = "2+ oy"

        # Hamyon balansini tekshirish
        try:
            from accounts.models import Wallet
            wallet = Wallet.objects.get(user=request.user)
            current_balance = wallet.balance
        except Wallet.DoesNotExist:
            current_balance = 0

        if current_balance < min_balance:
            return Response({
                'detail': f'Liniyaga chiqish uchun hisobingizda kamida {min_balance:,} UZS bo\'lishi kerak ({month_label}). Hozirgi balans: {int(current_balance):,} UZS.',
                'min_balance': min_balance,
                'current_balance': int(current_balance),
                'month_label': month_label,
            }, status=status.HTTP_403_FORBIDDEN)

        # GPS tekshiruvi
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        if not lat or not lng:
            return Response(
                {'detail': 'Onlaynga chiqish uchun joylashuvingiz (GPS) yoqilgan bo\'lishi shart.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        driver.current_lat = lat
        driver.current_lng = lng
        driver.is_online = True
        driver.save(update_fields=['is_online', 'current_lat', 'current_lng', 'updated_at'])
    else:
        # Going offline
        driver.is_online = False
        driver.save(update_fields=['is_online', 'updated_at'])

    return Response({
        'is_online': driver.is_online,
        'detail': 'Onlayn' if driver.is_online else 'Oflayn',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_driver_location(request):
    """Update driver's current location."""
    serializer = DriverLocationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        driver = request.user.driver_profile
        if driver.status != 'approved':
            return Response({'detail': 'Profilingiz tasdiqlanmagan.'}, status=status.HTTP_403_FORBIDDEN)
        if not driver.is_online:
            return Response({'detail': 'Siz oflaynsiz. Avval ish boshlash tugmasini bosing.'}, status=status.HTTP_400_BAD_REQUEST)
    except Driver.DoesNotExist:
        return Response(
            {'detail': 'Haydovchi profili topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    driver.current_lat = serializer.validated_data['lat']
    driver.current_lng = serializer.validated_data['lng']
    driver.save(update_fields=['current_lat', 'current_lng', 'updated_at'])

    return Response({'status': 'ok'})


class AdminUserListView(generics.ListCreateAPIView):
    """Admin-only: List and Create passengers."""
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(role='passenger')

    def get_serializer_class(self):
        from .serializers import AdminUserCRUDSerializer
        if self.request.method == 'POST':
            return AdminUserCRUDSerializer
        return UserProfileSerializer

class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin-only: Retrieve, Update, Delete passenger."""
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(role='passenger')

    def get_serializer_class(self):
        from .serializers import AdminUserCRUDSerializer
        if self.request.method in ['PUT', 'PATCH']:
            return AdminUserCRUDSerializer
        return UserProfileSerializer

class AdminDriverListView(generics.ListCreateAPIView):
    """Admin-only: List and Create drivers with profile info."""
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Driver.objects.all().select_related('user', 'vehicle')

    def create(self, request, *args, **kwargs):
        # Create user
        data = request.data
        if User.objects.filter(phone=data.get('phone')).exists():
            return Response({'error': 'Ushbu telefon raqam band.'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = User.objects.create(
            phone=data.get('phone'),
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            role='driver',
            is_verified=True,
            is_active=True
        )
        password = data.get('password')
        if password:
            user.set_password(password)
        else:
            user.set_password('taksi123')
        user.save()

        # Create vehicle
        vehicle = Vehicle.objects.create(
            make=data.get('vehicle_make', ''),
            model=data.get('vehicle_model', ''),
            plate_number=data.get('plate_number', ''),
            color=data.get('vehicle_color', ''),
            vehicle_type='standard'
        )

        # Create driver profile
        driver = Driver.objects.create(
            user=user,
            vehicle=vehicle,
            license_number=data.get('license_number', ''),
            status='approved'
        )

        return Response(DriverProfileSerializer(driver).data, status=status.HTTP_201_CREATED)

class AdminDriverDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin-only: Retrieve, Update, Delete driver."""
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Driver.objects.all().select_related('user', 'vehicle')

    def update(self, request, *args, **kwargs):
        driver = self.get_object()
        data = request.data
        user = driver.user
        vehicle = driver.vehicle

        # Update User
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        if data.get('password'):
            user.set_password(data.get('password'))
        if data.get('phone') and user.phone != data.get('phone'):
            if User.objects.filter(phone=data.get('phone')).exists():
                return Response({'error': 'Ushbu telefon raqam band.'}, status=status.HTTP_400_BAD_REQUEST)
            user.phone = data.get('phone')
        user.save()

        # Update Vehicle
        vehicle.make = data.get('vehicle_make', vehicle.make)
        vehicle.model = data.get('vehicle_model', vehicle.model)
        vehicle.plate_number = data.get('plate_number', vehicle.plate_number)
        vehicle.color = data.get('vehicle_color', vehicle.color)
        vehicle.save()

        # Update Driver
        driver.license_number = data.get('license_number', driver.license_number)
        driver.save()

        return Response(DriverProfileSerializer(driver).data)
        
    def perform_destroy(self, instance):
        user = instance.user
        vehicle = instance.vehicle
        instance.delete()
        if vehicle:
            vehicle.delete()
        if user:
            user.delete()


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_user_action(request, user_id):
    """Admin-only: Toggle user is_active status."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'Foydalanuvchi topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action')
    if action == 'toggle_active':
        user.is_active = not user.is_active
        user.save()
    return Response(UserProfileSerializer(user).data)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_driver_action(request, driver_id):
    """Admin-only: Approve, reject or block a driver."""
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action')
    if action == 'approve':
        driver.status = 'approved'
        driver.user.is_verified = True
        driver.user.save()

        # Kirish davri boshlash vaqtini tasdiqlanish paytiga o'rnatish
        if not driver.intro_period_start:
            driver.intro_period_start = timezone.now()
            driver.save(update_fields=['intro_period_start'])

        # Yangi haydovchiga 10,000 UZS kirish bonusi
        from django.conf import settings as conf_settings
        from accounts.models import Wallet
        bonus = conf_settings.DRIVER_BALANCE['SIGNUP_BONUS']
        wallet, created = Wallet.objects.get_or_create(user=driver.user)
        if created or wallet.balance == 0:
            wallet.deposit(bonus, f"Kirish bonusi: {bonus:,} UZS")

    elif action == 'reject':
        driver.status = 'rejected'
    elif action == 'block':
        driver.status = 'blocked'
        driver.user.is_active = False
        driver.user.save()
    elif action == 'toggle_active':
        driver.user.is_active = not driver.user.is_active
        driver.user.save()
    else:
        return Response({'detail': 'Noto\'g\'ri amal.'}, status=status.HTTP_400_BAD_REQUEST)

    driver.save()
    return Response(DriverProfileSerializer(driver).data)


# ============ SAVED LOCATIONS ============

class SavedLocationListCreateView(generics.ListCreateAPIView):
    """List and create saved locations for the authenticated user."""
    serializer_class = SavedLocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedLocation.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SavedLocationDeleteView(generics.DestroyAPIView):
    """Delete a saved location."""
    serializer_class = SavedLocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedLocation.objects.filter(user=self.request.user)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recommendations(request):
    """Get smart recommendations for drivers based on real demand and distance."""
    try:
        driver = request.user.driver_profile
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi profili topilmadi.'}, status=404)

    # Districts with their center coordinates
    districts = [
        {'name': 'Yunusobod', 'lat': 41.3650, 'lng': 69.2882},
        {'name': 'Chilonzor', 'lat': 41.2785, 'lng': 69.2081},
        {'name': 'Mirzo Ulug\'bek', 'lat': 41.3195, 'lng': 69.3274},
        {'name': 'Yakkasaroy', 'lat': 41.2825, 'lng': 69.2541},
        {'name': 'Shayxontohur', 'lat': 41.3111, 'lng': 69.2222},
        {'name': 'Olmazor', 'lat': 41.3411, 'lng': 69.2081},
        {'name': 'Sergeli', 'lat': 41.2211, 'lng': 69.2381},
    ]

    from pricing.engine import haversine
    import random

    # Current driver location
    d_lat = driver.current_lat or 41.3111
    d_lng = driver.current_lng or 69.2401

    # Filter out current district (roughly) and sort by distance
    # We want districts that are NOT too far but NOT where the driver already is
    scored_districts = []
    for dist in districts:
        dist_km = haversine(d_lat, d_lng, dist['lat'], dist['lng'])
        # Scored by demand (random for now) / distance
        # We prefer districts between 2km and 8km
        if 2.0 <= dist_km <= 10.0:
            scored_districts.append(dist)

    if not scored_districts:
        # Fallback to random if none in range
        selected = random.choice(districts)
    else:
        selected = random.choice(scored_districts)
    
    return Response({
        'name': selected['name'],
        'lat': selected['lat'],
        'lng': selected['lng'],
        'reason': f"Ushbu hududda hozirda talab yuqori va haydovchilar kam.",
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_view(request):
    """Get user wallet balance and history."""
    from .models import Wallet
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    serializer = WalletSerializer(wallet)
    return Response(serializer.data)


def _tg_send(token, chat_id, text, parse_mode='HTML', reply_markup=None):
    """Telegram ga xabar yuborish — helper."""
    import requests as req_lib
    import json
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        req_lib.post(url, data=data, timeout=8)
    except Exception as e:
        logger.error("Telegram xabar yuborishda xatolik: %s", e)


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_webhook(request):
    """
    Telegram Bot Webhook — polling emas, Telegram o'zi POST yuboradi.

    Polling (`run_bot`) Railway'da 409 Conflict beradi — bir nechta instance.
    Webhook bilan bu muammo yo'q: Telegram faqat bizning serverga yuboradi.

    Ro'yxatdan o'tish: start.sh da webhook registratsiyasi qilinadi.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return Response({'status': 'no_token'}, status=200)

    data = request.data
    message = data.get('message', {})
    if not message:
        return Response({'status': 'ok'}, status=200)

    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '')
    contact = message.get('contact')

    if not chat_id:
        return Response({'status': 'ok'}, status=200)

    if text == '/start':
        welcome = (
            "🚕 <b>Goldride</b> botiga xush kelibsiz!\n\n"
            "📱 Tizimga kirish uchun telefon raqamingizni yuboring.\n"
            "Sizga 6 xonali tasdiqlash kodi yuboriladi."
        )
        reply_markup = {
            'keyboard': [[{'text': '📱 Telefon raqamni yuborish', 'request_contact': True}]],
            'resize_keyboard': True,
            'one_time_keyboard': True,
        }
        _tg_send(token, chat_id, welcome, reply_markup=reply_markup)

    elif contact:
        from .models import TelegramOTP
        phone = contact.get('phone_number', '')
        if not phone.startswith('+'):
            phone = '+' + phone

        otp_entry = TelegramOTP.create_otp(phone, chat_id=chat_id)
        otp = otp_entry.otp

        user = User.objects.filter(phone=phone).first()
        if user:
            msg = (
                f"✅ <b>Akkauntingiz topildi!</b>\n\n"
                f"Ilovaga kirish uchun kodni kiriting:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa amal qiladi."
            )
        else:
            msg = (
                f"📱 Telefon: <code>{phone}</code>\n\n"
                f"Ilovaga kirish kodi:\n\n"
                f"🔑 <b>{otp}</b>\n\n"
                f"⏱ Kod 5 daqiqa amal qiladi.\n\n"
                f"❗ Yangi foydalanuvchi — ilovada ro'yxatdan o'ting."
            )

        _tg_send(token, chat_id, msg)
        logger.info("Telegram OTP yuborildi: %s (webhook)", phone)

    else:
        _tg_send(token, chat_id, "Iltimos, pastdagi tugmani bosib telefon raqamingizni yuboring.")

    return Response({'status': 'ok'}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_view(request):
    """
    Handle Google OAuth callback/token.
    Requires: email, first_name, last_name, and then asks for phone.
    """
    email = request.data.get('email')
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')
    phone = request.data.get('phone') # Might be empty if it's the first step

    if not email:
        return Response({'detail': 'Email shart.'}, status=400)

    # Try to find user by email or phone
    user = User.objects.filter(email=email).first()
    
    if not user and phone:
        # If we have phone, we can create the user
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'username': phone,
                'is_verified': True
            }
        )
        if created:
            from accounts.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet.deposit(20000, "Xush kelibsiz (Google orqali)")
    
    if not user:
        return Response({
            'detail': 'Ro\'yxatdan o\'tish uchun telefon raqami kerak.',
            'step': 'provide_phone',
            'email': email,
            'first_name': first_name,
            'last_name': last_name
        }, status=200)

    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserProfileSerializer(user).data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deposit_wallet_view(request):
    """Deposit money to wallet."""
    from .models import Wallet
    amount = request.data.get('amount')
    if not amount or float(amount) <= 0:
        return Response({'detail': 'Noto\'g\'ri miqdor.'}, status=status.HTTP_400_BAD_REQUEST)
    
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    wallet.deposit(float(amount))
    return Response({
        'detail': f'{amount} tanga muvaffaqiyatli qo\'shildi.',
        'balance': wallet.balance
    })
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def wallet_requests_view(request):
    if request.method == 'GET':
        requests = request.user.wallet_requests.all()
        serializer = WalletRequestSerializer(requests, many=True)
        return Response(serializer.data)
    
    if request.method == 'POST':
        serializer = WalletRequestSerializer(data=request.data)
        if serializer.is_valid():
            wallet_req = serializer.save(user=request.user)
            
            # Send Telegram Notification to Admin
            req_type_label = "To'ldirish" if wallet_req.request_type == 'deposit' else "Yechish"
            message = (
                f"💰 <b>Yangi Hamyon So'rovi!</b>\n\n"
                f"👤 Foydalanuvchi: {request.user.get_full_name()} ({request.user.phone})\n"
                f"🔹 Tur: {req_type_label}\n"
                f"💵 Miqdor: {wallet_req.amount} UZS\n"
                f"✈️ Telegram: @{request.user.telegram_username or 'Kiritilmagan'}\n"
                f"📅 Vaqt: {wallet_req.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"<i>Iltimos, admin panel orqali tasdiqlang yoki rad eting.</i>"
            )
            send_telegram_notification(message)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============ HAYDOVCHI MAQSADLARI ============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_goals_view(request):
    """Barcha faol maqsadlar va haydovchining joriy taraqqiyoti."""
    from .models import DriverGoal, GoalProgress
    from django.utils import timezone

    try:
        driver = request.user.driver_profile
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi profili topilmadi.'}, status=404)

    goals = DriverGoal.objects.filter(is_active=True)
    today = timezone.now().date()

    # Haydovchining faol maqsadini topish
    active_progress = GoalProgress.objects.filter(
        driver=driver, status='active'
    ).select_related('goal').first()

    result = []
    for goal in goals:
        result.append({
            'id': goal.id,
            'title': goal.title,
            'min_rides': goal.min_rides,
            'bonus_amount': goal.bonus_amount,
            'extra_orders_bonus': goal.extra_orders_bonus,
            'commission_discount_percent': goal.commission_discount_percent,
            'commission_discount_days': goal.commission_discount_days,
            'period_days': goal.period_days,
            'is_selected': active_progress and active_progress.goal_id == goal.id,
            'current_count': active_progress.current_count if (active_progress and active_progress.goal_id == goal.id) else 0,
            'end_date': str(active_progress.end_date) if (active_progress and active_progress.goal_id == goal.id) else None,
        })

    return Response({
        'goals': result,
        'active_goal_id': active_progress.goal_id if active_progress else None,
        'commission_discount_until': str(driver.commission_discount_until) if driver.commission_discount_until else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_goal_select_view(request):
    """Haydovchi maqsad tanlaydi (oldindan tanlash shart)."""
    from .models import DriverGoal, GoalProgress
    from django.utils import timezone
    from datetime import timedelta

    try:
        driver = request.user.driver_profile
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi profili topilmadi.'}, status=404)

    goal_id = request.data.get('goal_id')
    if not goal_id:
        return Response({'detail': 'goal_id kiritilishi shart.'}, status=400)

    # Avval faol maqsad bormi?
    existing = GoalProgress.objects.filter(driver=driver, status='active').first()
    if existing:
        return Response({
            'detail': 'Sizda allaqachon faol maqsad bor. Uni tugatgandan yoki muddati o\'tganidan keyin yangi tanlang.',
            'end_date': str(existing.end_date),
        }, status=400)

    try:
        goal = DriverGoal.objects.get(id=goal_id, is_active=True)
    except DriverGoal.DoesNotExist:
        return Response({'detail': 'Maqsad topilmadi.'}, status=404)

    today = timezone.now().date()
    progress = GoalProgress.objects.create(
        driver=driver,
        goal=goal,
        start_date=today,
        end_date=today + timedelta(days=goal.period_days),
        status='active',
    )

    logger.info("Maqsad tanlandi: %s → %s (tugash: %s)", driver.user.phone, goal.title, progress.end_date)

    return Response({
        'detail': f"Maqsad tanlandi: {goal.title}",
        'start_date': str(progress.start_date),
        'end_date': str(progress.end_date),
        'goal': {
            'min_rides': goal.min_rides,
            'bonus_amount': goal.bonus_amount,
            'period_days': goal.period_days,
        }
    })


# ============ REFERRAL BONUS YECHISH ============

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw_referral_view(request):
    """Referral bonusni kartaga yechib olish (2% komissiya, min 1000 UZS qoldiq)."""
    from accounts.cashback import withdraw_referral_bonus

    amount_raw = request.data.get('amount')
    if not amount_raw:
        return Response({'detail': 'Miqdor kiritilishi shart.'}, status=400)

    try:
        amount = Decimal(str(amount_raw))
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        return Response({'detail': 'Noto\'g\'ri miqdor.'}, status=400)

    success, message = withdraw_referral_bonus(request.user, amount)
    if not success:
        return Response({'detail': message}, status=400)

    return Response({'detail': message})


# ============ TAKSI PARK ============

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def taxi_park_register_view(request):
    """Yangi taksi parkini ro'yxatdan o'tkazish (saytdan)."""
    from .models import TaxiPark
    data = request.data
    required = ['name', 'phone', 'contact_person']
    for field in required:
        if not data.get(field):
            return Response({'detail': f'{field} majburiy.'}, status=400)

    if TaxiPark.objects.filter(phone=data['phone']).exists():
        return Response({'detail': 'Bu telefon raqam allaqachon ro\'yxatdan o\'tgan.'}, status=400)

    park = TaxiPark.objects.create(
        name=data['name'],
        phone=data['phone'],
        contact_person=data['contact_person'],
        address=data.get('address', ''),
        inn=data.get('inn', ''),
        description=data.get('description', ''),
        status='pending',
    )
    logger.info("Yangi taksi park: %s (%s)", park.name, park.phone)
    return Response({
        'detail': 'Ro\'yxatdan o\'tdingiz. Admin tasdiqlaganidan keyin xabardor qilamiz.',
        'park_id': park.id,
    }, status=201)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def taxi_park_list_public_view(request):
    """Tasdiqlangan taksi parklarini ko'rsatish (haydovchi ro'yxatdan o'tishda tanlash uchun)."""
    from .models import TaxiPark
    parks = TaxiPark.objects.filter(status='approved').values('id', 'name', 'address', 'driver_count')
    return Response(list(parks))


class AdminTaxiParkListView(generics.ListAPIView):
    """Admin: barcha taksi parklari ro'yxati."""
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        from .models import TaxiPark
        return TaxiPark.objects.all().order_by('-created_at')

    def list(self, request, *args, **kwargs):
        from .models import TaxiPark
        parks = TaxiPark.objects.all().order_by('-created_at')
        data = []
        for p in parks:
            data.append({
                'id': p.id,
                'name': p.name,
                'phone': p.phone,
                'contact_person': p.contact_person,
                'address': p.address,
                'inn': p.inn,
                'status': p.status,
                'driver_count': p.driver_count,
                'api_token': p.api_token,
                'created_at': p.created_at,
            })
        return Response(data)


class AdminTaxiParkDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin: taksi park detail."""
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        from .models import TaxiPark
        return TaxiPark.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class TaxiParkSerializer(serializers.ModelSerializer):
            driver_count = serializers.SerializerMethodField()
            def get_driver_count(self, obj): return obj.driver_count
            class Meta:
                from accounts.models import TaxiPark as TP
                model = TP
                fields = '__all__'
        return TaxiParkSerializer


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_taxi_park_action(request, park_id):
    """Admin: taksi parkni tasdiqlash/bloklash."""
    from .models import TaxiPark
    try:
        park = TaxiPark.objects.get(id=park_id)
    except TaxiPark.DoesNotExist:
        return Response({'detail': 'Park topilmadi.'}, status=404)

    action = request.data.get('action')
    if action == 'approve':
        park.status = 'approved'
    elif action == 'reject':
        park.status = 'rejected'
    elif action == 'block':
        park.status = 'blocked'
    else:
        return Response({'detail': 'Noto\'g\'ri amal.'}, status=400)

    park.save(update_fields=['status'])
    return Response({'status': park.status, 'detail': f'{park.name} → {park.status}'})


class AdminTaxiParkDriversView(generics.ListAPIView):
    """Admin: taksi park haydovchilari ro'yxati."""
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Driver.objects.filter(
            taxi_park_id=self.kwargs['park_id']
        ).select_related('user', 'vehicle')


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_taxi_park_add_driver(request, park_id):
    """Admin: taksi parkka yangi haydovchi qo'shish (to'liq ma'lumot bilan)."""
    from .models import TaxiPark, Vehicle, Wallet
    try:
        park = TaxiPark.objects.get(id=park_id)
    except TaxiPark.DoesNotExist:
        return Response({'detail': 'Park topilmadi.'}, status=404)

    data = request.data
    phone = data.get('phone')
    if not phone:
        return Response({'detail': 'Telefon raqami majburiy.'}, status=400)

    if User.objects.filter(phone=phone).exists():
        return Response({'detail': 'Bu telefon raqam allaqachon ro\'yxatda.'}, status=400)

    user = User.objects.create(
        phone=phone,
        first_name=data.get('first_name', ''),
        last_name=data.get('last_name', ''),
        role='driver',
        is_verified=True,
        is_active=True,
    )
    password = data.get('password', 'taksi123')
    user.set_password(password)
    user.save()

    vehicle = Vehicle.objects.create(
        make=data.get('vehicle_make', ''),
        model=data.get('vehicle_model', ''),
        plate_number=data.get('plate_number', ''),
        color=data.get('vehicle_color', 'white'),
        year=data.get('year', 2020),
        vehicle_type=data.get('vehicle_type', 'sedan'),
    )

    driver = Driver.objects.create(
        user=user,
        vehicle=vehicle,
        license_number=data.get('license_number', ''),
        taxi_park=park,
        status='approved',
        intro_period_start=timezone.now(),
    )

    from django.conf import settings as conf_settings
    bonus = conf_settings.DRIVER_BALANCE['SIGNUP_BONUS']
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet.deposit(bonus, f"Kirish bonusi — {park.name} parki")

    return Response(DriverProfileSerializer(driver).data, status=201)


# ============ TAKSI PARK PORTAL ============

def _get_park_from_token(request):
    """Authorization: Token <api_token> yoki Bearer <api_token> orqali park olish."""
    from .models import TaxiPark
    auth = request.headers.get('Authorization', '')
    token = None
    if auth.startswith('Token '):
        token = auth[6:]
    elif auth.startswith('Bearer '):
        token = auth[7:]
    if not token:
        return None
    return TaxiPark.objects.filter(api_token=token, status='approved').first()


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def taxi_park_login_view(request):
    """Taksi park portali uchun login: telefon + parol → api_token qaytaradi."""
    from .models import TaxiPark
    phone = request.data.get('phone')
    password = request.data.get('password')
    if not phone or not password:
        return Response({'detail': 'Telefon va parol kiritilishi shart.'}, status=400)

    park = TaxiPark.objects.filter(phone=phone).first()
    if not park:
        return Response({'detail': 'Park topilmadi.'}, status=401)
    if park.status == 'pending':
        return Response({'detail': 'Parkingiz hali tasdiqlanmagan. Admin tasdiqlashini kuting.'}, status=403)
    if park.status in ('rejected', 'blocked'):
        return Response({'detail': f'Parkingiz {park.get_status_display()}. Admin bilan bog\'laning.'}, status=403)

    # Parol — parkni ro'yxatdan o'tkazganda o'rnatilgan (API token = parol sifatida ishlatiladi yoki alohida parol)
    # Soddalik uchun: parol = api_token ning dastlabki 8 belgisi
    if not (password == park.api_token[:8] or password == park.api_token):
        return Response({'detail': 'Noto\'g\'ri parol.'}, status=401)

    return Response({
        'token': park.api_token,
        'park': {
            'id': park.id,
            'name': park.name,
            'phone': park.phone,
            'contact_person': park.contact_person,
            'address': park.address,
            'driver_count': park.driver_count,
            'status': park.status,
        }
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def taxi_park_me_view(request):
    """Joriy park ma'lumotlari."""
    park = _get_park_from_token(request)
    if not park:
        return Response({'detail': 'Token yaroqsiz.'}, status=401)
    return Response({
        'id': park.id, 'name': park.name, 'phone': park.phone,
        'contact_person': park.contact_person, 'address': park.address,
        'inn': park.inn, 'driver_count': park.driver_count, 'status': park.status,
    })


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
def taxi_park_drivers_view(request):
    """Park haydovchilari: ro'yxat (GET) va yangi qo'shish (POST)."""
    park = _get_park_from_token(request)
    if not park:
        return Response({'detail': 'Token yaroqsiz.'}, status=401)

    if request.method == 'GET':
        drivers = Driver.objects.filter(taxi_park=park).select_related('user', 'vehicle')
        return Response(DriverProfileSerializer(drivers, many=True).data)

    # POST — yangi haydovchi
    from .models import Vehicle, Wallet
    data = request.data
    phone = data.get('phone')
    if not phone:
        return Response({'detail': 'Telefon majburiy.'}, status=400)
    if User.objects.filter(phone=phone).exists():
        return Response({'detail': 'Bu telefon allaqachon ro\'yxatda.'}, status=400)

    user = User.objects.create(
        phone=phone, first_name=data.get('first_name', ''),
        last_name=data.get('last_name', ''), role='driver',
        is_verified=True, is_active=True,
    )
    user.set_password(data.get('password', 'taksi123'))
    user.save()

    vehicle = Vehicle.objects.create(
        make=data.get('vehicle_make', ''), model=data.get('vehicle_model', ''),
        plate_number=data.get('plate_number', ''), color=data.get('vehicle_color', 'white'),
        year=data.get('year', 2020), vehicle_type=data.get('vehicle_type', 'sedan'),
    )

    from django.conf import settings as conf
    driver = Driver.objects.create(
        user=user, vehicle=vehicle,
        license_number=data.get('license_number', ''),
        taxi_park=park, status='approved',
        intro_period_start=timezone.now(),
    )
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet.deposit(conf.DRIVER_BALANCE['SIGNUP_BONUS'], f"Kirish bonusi — {park.name}")
    return Response(DriverProfileSerializer(driver).data, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.AllowAny])
def taxi_park_driver_detail_view(request, driver_id):
    """Park haydovchi detail: ko'rish, tahrirlash, o'chirish."""
    park = _get_park_from_token(request)
    if not park:
        return Response({'detail': 'Token yaroqsiz.'}, status=401)

    try:
        driver = Driver.objects.get(id=driver_id, taxi_park=park)
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi topilmadi.'}, status=404)

    if request.method == 'GET':
        return Response(DriverProfileSerializer(driver).data)

    if request.method == 'PUT':
        data = request.data
        user = driver.user
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        if data.get('password'):
            user.set_password(data['password'])
        user.save()
        if driver.vehicle:
            v = driver.vehicle
            v.make  = data.get('vehicle_make', v.make)
            v.model = data.get('vehicle_model', v.model)
            v.plate_number = data.get('plate_number', v.plate_number)
            v.color = data.get('vehicle_color', v.color)
            v.save()
        driver.license_number = data.get('license_number', driver.license_number)
        action = data.get('action')
        if action == 'block':
            driver.status = 'blocked'
        elif action == 'activate':
            driver.status = 'approved'
        driver.save()
        return Response(DriverProfileSerializer(driver).data)

    if request.method == 'DELETE':
        user = driver.user
        if driver.vehicle:
            driver.vehicle.delete()
        driver.delete()
        user.delete()
        return Response({'detail': 'Haydovchi o\'chirildi.'}, status=204)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def taxi_park_stats_view(request):
    """Park statistikasi: haydovchilar, safarlar, daromad."""
    from rides.models import Ride, RideRequest
    from django.db.models import Sum, Count
    from datetime import timedelta

    park = _get_park_from_token(request)
    if not park:
        return Response({'detail': 'Token yaroqsiz.'}, status=401)

    drivers = Driver.objects.filter(taxi_park=park)
    driver_ids = list(drivers.values_list('id', flat=True))

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Jami safarlar
    total_rides = Ride.objects.filter(driver_id__in=driver_ids, status='completed').count()
    today_rides = Ride.objects.filter(driver_id__in=driver_ids, status='completed', completed_at__gte=today_start).count()

    # Daromad
    earnings = Ride.objects.filter(driver_id__in=driver_ids, status='completed').aggregate(
        total=Sum('driver_earnings'), commission=Sum('commission_amount')
    )

    # So'nggi 7 kun statistikasi (grafiklar uchun)
    daily_data = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        count = Ride.objects.filter(
            driver_id__in=driver_ids, status='completed',
            completed_at__gte=day_start, completed_at__lt=day_end
        ).count()
        income = Ride.objects.filter(
            driver_id__in=driver_ids, status='completed',
            completed_at__gte=day_start, completed_at__lt=day_end
        ).aggregate(s=Sum('driver_earnings'))['s'] or 0
        daily_data.append({
            'date': day_start.strftime('%d.%m'),
            'rides': count,
            'income': int(income),
        })

    return Response({
        'total_drivers': drivers.count(),
        'online_drivers': drivers.filter(is_online=True).count(),
        'approved_drivers': drivers.filter(status='approved').count(),
        'pending_drivers': drivers.filter(status='pending').count(),
        'total_rides': total_rides,
        'today_rides': today_rides,
        'total_earnings': int(earnings['total'] or 0),
        'total_commission': int(earnings['commission'] or 0),
        'daily': daily_data,
    })
