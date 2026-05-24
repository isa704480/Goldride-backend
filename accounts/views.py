from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from decimal import Decimal
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import Driver, SavedLocation, User
from .otp import send_otp, verify_otp, get_otp_ttl
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

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp_view(request):
    """Send OTP to phone number or email."""
    phone = request.data.get('phone')
    email = request.data.get('email')

    if not phone and not email:
        return Response({'detail': 'Telefon raqami yoki email kiritish shart.'}, status=400)

    # Use email for OTP delivery if provided, but phone for identification
    identifier = email if email else phone

    # Check rate limiting
    ttl = get_otp_ttl(identifier)
    if ttl > 240:
        return Response(
            {'detail': f'{ttl - 240} soniyadan keyin qayta urinib ko\'ring.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

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

    # --- TELEGRAM 6-digit OTP flow ---
    if tg_login and phone and otp:
        from django.core.cache import cache as django_cache
        if not phone.startswith('+'): phone = '+' + phone
        stored_otp = django_cache.get(f'tg_otp:{phone}')
        if not stored_otp or stored_otp != str(otp):
            return Response({'detail': 'Kod noto\'g\'ri yoki muddati o\'tgan.'}, status=400)

        chat_id = django_cache.get(f'tg_chat:{phone}')
        django_cache.delete(f'tg_otp:{phone}')
        django_cache.delete(f'tg_chat:{phone}')

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


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_login_view(request):
    """Secure login for admin panel using phone + password."""
    phone = request.data.get('phone')
    password = request.data.get('password')

    if not phone or not password:
        return Response({'error': 'Telefon va parolni kiriting'}, status=status.HTTP_400_BAD_REQUEST)

    print(f"Login attempt: {phone}") # Debug
    
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

        # === Yangi haydovchiga boshlang'ich bonus berish ===
        from django.conf import settings as conf_settings
        from accounts.models import Wallet, WalletTransaction
        bonus = conf_settings.DRIVER_BALANCE['SIGNUP_BONUS']
        wallet, created = Wallet.objects.get_or_create(user=driver.user)
        if created or wallet.balance == 0:
            wallet.deposit(bonus, f"Yangi haydovchi bonusi ({bonus:,} UZS)")

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


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_webhook(request):
    """
    Telegram Bot Webhook handle:
    If message contains a contact, create/login user and give bonus.
    """
    data = request.data
    message = data.get('message', {})
    contact = message.get('contact')

    if contact:
        phone = contact.get('phone_number')
        if not phone.startswith('+'):
            phone = '+' + phone
        
        first_name = contact.get('first_name', '')
        last_name = contact.get('last_name', '')
        tg_id = contact.get('user_id')

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'username': phone,
                'is_verified': True
            }
        )

        if created:
            from accounts.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet.deposit(20000, "Xush kelibsiz (Telegram orqali)")

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # In real life, we would notify the user via bot that they are logged in
        return Response({
            'status': 'ok',
            'user': UserProfileSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })

    return Response({'status': 'ignored'}, status=200)


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
