from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Driver, Vehicle, SavedLocation, Wallet, WalletTransaction, WalletRequest

User = get_user_model()


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13, required=False)
    email = serializers.EmailField(required=False)

    def validate_phone(self, value):
        if value and (not value.startswith('+998') or len(value) != 13):
            raise serializers.ValidationError(
                "Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak."
            )
        return value


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13)
    otp = serializers.CharField(max_length=6)


class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone', 'first_name', 'last_name', 'role', 'avatar', 'language']
        read_only_fields = ['phone']


class UserProfileSerializer(serializers.ModelSerializer):
    has_driver_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'phone', 'first_name', 'last_name',
            'role', 'avatar', 'language', 'is_verified',
            'has_driver_profile', 'gold_points', 'bank_account_id',
            'id_number', 'referral_code', 'telegram_username', 'telegram_chat_id',
            'passenger_rating', 'total_passenger_rides', 'has_agreed_to_terms',
            'created_at', 'is_active'
        ]
        read_only_fields = ['id', 'phone', 'is_verified', 'gold_points', 'id_number', 'referral_code', 'passenger_rating', 'total_passenger_rides', 'has_agreed_to_terms', 'created_at', 'is_active']

    def get_has_driver_profile(self, obj):
        return hasattr(obj, 'driver_profile')


class VehicleSerializer(serializers.ModelSerializer):
    color_display = serializers.CharField(source='get_color_display', read_only=True)
    type_display = serializers.CharField(source='get_vehicle_type_display', read_only=True)
    car_class_display = serializers.CharField(source='get_car_class_display', read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'make', 'model', 'year', 'color', 'color_display',
            'plate_number', 'vehicle_type', 'type_display', 'car_class', 'car_class_display', 
            'photo', 'photo_back', 'photo_left', 'photo_right', 'interior_photo_1', 'interior_photo_2',
            'tech_passport_photo_front', 'tech_passport_photo_back'
        ]


class DriverRegistrationSerializer(serializers.Serializer):
    license_number = serializers.CharField(max_length=20)
    license_photo = serializers.ImageField(required=False)
    # Vehicle fields
    make = serializers.CharField(max_length=50)
    vehicle_model = serializers.CharField(max_length=50)
    year = serializers.IntegerField()
    color = serializers.CharField(max_length=10)
    plate_number = serializers.CharField(max_length=15)
    vehicle_type = serializers.CharField(max_length=10, default='sedan')
    vehicle_photo = serializers.ImageField(required=False)
    # New document fields
    license_photo_back = serializers.ImageField(required=False)
    passport_photo_front = serializers.ImageField(required=False)
    passport_photo_back = serializers.ImageField(required=False)
    face_id_photo = serializers.ImageField(required=False)
    taxi_license_photo = serializers.FileField(required=False)
    # New vehicle fields
    photo_back = serializers.ImageField(required=False)
    photo_left = serializers.ImageField(required=False)
    photo_right = serializers.ImageField(required=False)
    interior_photo_1 = serializers.ImageField(required=False)
    interior_photo_2 = serializers.ImageField(required=False)
    tech_passport_photo_front = serializers.ImageField(required=False)
    tech_passport_photo_back = serializers.ImageField(required=False)
    # Agreement
    has_agreed_to_terms = serializers.BooleanField(default=False)

    def create(self, validated_data):
        user = self.context['request'].user
        user.role = 'driver'
        user.is_verified = True
        user.save()

        driver = Driver.objects.create(
            user=user,
            license_number=validated_data['license_number'],
            license_photo=validated_data.get('license_photo'),
            license_photo_back=validated_data.get('license_photo_back'),
            passport_photo_front=validated_data.get('passport_photo_front'),
            passport_photo_back=validated_data.get('passport_photo_back'),
            face_id_photo=validated_data.get('face_id_photo'),
            taxi_license_photo=validated_data.get('taxi_license_photo'),
            status='approved'
        )

        # Give welcome signup bonus to wallet
        from django.conf import settings as conf_settings
        from accounts.models import Wallet
        bonus = 50000
        if hasattr(conf_settings, 'DRIVER_BALANCE') and 'SIGNUP_BONUS' in conf_settings.DRIVER_BALANCE:
            bonus = conf_settings.DRIVER_BALANCE['SIGNUP_BONUS']
        
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.deposit(bonus, f"Yangi haydovchi bonusi ({bonus:,} UZS)")

        Vehicle.objects.create(
            driver=driver,
            make=validated_data['make'],
            model=validated_data['vehicle_model'],
            year=validated_data['year'],
            color=validated_data['color'],
            plate_number=validated_data['plate_number'],
            vehicle_type=validated_data.get('vehicle_type', 'sedan'),
            photo=validated_data.get('vehicle_photo'),
            photo_back=validated_data.get('photo_back'),
            photo_left=validated_data.get('photo_left'),
            photo_right=validated_data.get('photo_right'),
            interior_photo_1=validated_data.get('interior_photo_1'),
            interior_photo_2=validated_data.get('interior_photo_2'),
            tech_passport_photo_front=validated_data.get('tech_passport_photo_front'),
            tech_passport_photo_back=validated_data.get('tech_passport_photo_back'),
        )

        return driver


class DriverProfileSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    vehicle = VehicleSerializer(read_only=True)

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    net_earnings = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'user', 'license_number', 'status', 'status_display',
            'is_online', 'current_lat', 'current_lng', 'rating', 'total_rides',
            'total_earnings', 'commission_paid', 'net_earnings',
            'vehicle', 'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'rating', 'total_rides',
            'total_earnings', 'commission_paid', 'created_at'
        ]


class AdminUserCRUDSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'phone', 'first_name', 'last_name', 'role', 'language', 'is_active', 'password']
        
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        # Random UUID if no password is provided for regular users
        if password:
            user.set_password(password)
        else:
            user.set_password('taksi123') # Default password if empty
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminDriverCRUDSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = '__all__'


class DriverLocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class SavedLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedLocation
        fields = ['id', 'name', 'address', 'latitude', 'longitude', 'icon', 'created_at']
        read_only_fields = ['id', 'created_at']
class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ['id', 'transaction_type', 'amount', 'description', 'status', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    transactions = WalletTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Wallet
        fields = ['id', 'balance', 'is_active', 'updated_at', 'transactions']
        read_only_fields = ['id', 'balance', 'updated_at']

class WalletRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletRequest
        fields = [
            'id', 'user', 'request_type', 'amount', 'status', 
            'admin_comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'status', 'admin_comment', 'created_at', 'updated_at']


class DriverPublicRegistrationSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13)
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    license_number = serializers.CharField(max_length=20)
    make = serializers.CharField(max_length=50)
    vehicle_model = serializers.CharField(max_length=50)
    year = serializers.IntegerField()
    color = serializers.CharField(max_length=10)
    plate_number = serializers.CharField(max_length=15)
    vehicle_type = serializers.CharField(max_length=10, default='sedan')

    def validate_phone(self, value):
        if value and not value.startswith('+'):
            value = '+' + value
        if not value.startswith('+998') or len(value) != 13:
            raise serializers.ValidationError(
                "Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak."
            )
        return value

