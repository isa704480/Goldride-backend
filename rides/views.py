import logging
from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from django.utils import timezone
from django.db import models
from django.db.models import Q, Sum, Avg, Count, F
from datetime import timedelta
from decimal import Decimal

logger = logging.getLogger('rides')

from .models import Ride, RideRequest, RidePassenger, RideRating, RideStop, ChatMessage, EmergencyAlert
from accounts.models import Driver, FavoriteDriver, User
from accounts.serializers import DriverProfileSerializer
from .serializers import (
    RideSerializer,
    RideRequestSerializer,
    RideRequestCreateSerializer,
    RideRatingSerializer,
    PriceEstimateSerializer,
    RideStopSerializer,
    ChatMessageSerializer,
)
from pricing.engine import calculate_price, calculate_distance, get_active_pricing
from matching.engine import find_match
from accounts.gamification import update_driver_goals
from .utils import is_in_tashkent, notify_ride_status_update


@api_view(['POST'])
@permission_classes([AllowAny])
def estimate_price(request):
    """Get price estimate for a ride."""
    serializer = PriceEstimateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # === GEO-FENCING: Faqat Toshkent ichida ishlash ===
    if not is_in_tashkent(data['pickup_lat'], data['pickup_lng']):
        return Response(
            {'detail': 'Afsuski, hozircha ushbu hududda (olish manzili) xizmat ko\'rsata olmaymiz. Faqat Toshkent ichida ishlaymiz.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if not is_in_tashkent(data['drop_lat'], data['drop_lng']):
        return Response(
            {'detail': 'Afsuski, hozircha ushbu hududga (tushirish manzili) xizmat ko\'rsata olmaymiz. Faqat Toshkent ichida ishlaymiz.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    distance = calculate_distance(
        data['pickup_lat'], data['pickup_lng'],
        data['drop_lat'], data['drop_lng']
    )

    is_scheduled = data.get('is_scheduled', False)
    stops_count = data.get('stops_count', 0)

    # Calculate all options for all categories
    categories = ['economy', 'comfort', 'electro', 'business']
    prices = {}
    
    for cat in categories:
        prices[cat] = {
            'solo': calculate_price(distance, category=cat, share_type='solo', stops_count=stops_count, is_scheduled=is_scheduled),
            'shared_1': calculate_price(distance, category=cat, share_type='shared_1', partners_found=True, stops_count=stops_count, is_scheduled=is_scheduled),
            'shared_2': calculate_price(distance, category=cat, share_type='shared_2', partners_found=True, stops_count=stops_count, is_scheduled=is_scheduled),
        }

    return Response({
        'distance_km': round(distance, 2),
        'prices': prices,
        'currency': 'UZS',
        'estimated_duration_min': max(int(distance * 3), 5) + (stops_count * 3),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_ride(request):
    """Request a new ride."""
    serializer = RideRequestCreateSerializer(data=request.data)
    if not serializer.is_valid():
        print(f"[RIDE REQUEST ERROR] {serializer.errors}")
        print(f"[RIDE REQUEST DATA] {request.data}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data

    # === GEO-FENCING: Faqat Toshkent ichida ishlash ===
    if not is_in_tashkent(data['pickup_lat'], data['pickup_lng']) or not is_in_tashkent(data['drop_lat'], data['drop_lng']):
        return Response(
            {'detail': 'Afsuski, Goldride hozircha faqat Toshkent shahri ichida xizmat ko\'rsatadi.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # === ANTI-FRAUD: Bloklangan foydalanuvchi tekshiruvi ===
    user = request.user
    # if user.is_blocked:
    #     return Response(
    #         {'detail': 'Sizning akkauntingiz bekor qilishlar limiti oshib ketgani sababli bloklangan. Iltimos, qo\'llab-quvvatlash xizmatiga murojaat qiling.'},
    #         status=status.HTTP_403_FORBIDDEN
    #     )

    # Penalty balance check disabled as requested
    # if request.user.penalty_balance > 0:
    #     return Response(
    #         {'detail': f'Sizda {int(request.user.penalty_balance)} UZS jarima mavjud. Buyurtma berish uchun avval jarimani to\'lang.'},
    #         status=status.HTTP_403_FORBIDDEN
    #     )

    # Check if user already has a pending/active ride
    active = RideRequest.objects.filter(
        user=request.user,
        status__in=['pending', 'matched', 'accepted']
    ).exists()
    if active and not data.get('is_scheduled'):
        return Response(
            {'detail': 'Sizning faol safar so\'rovingiz mavjud.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Calculate price
    distance = calculate_distance(
        data['pickup_lat'], data['pickup_lng'],
        data['drop_lat'], data['drop_lng']
    )
    
    stops_data = data.get('stops', [])
    share_type = data.get('share_type', 'solo')
    price = calculate_price(
        distance, 
        category=data.get('car_category', 'economy'),
        share_type=share_type,
        partners_found=(share_type != 'solo'),
        stops_count=len(stops_data),
        is_scheduled=data.get('is_scheduled', False)
    )
    
    # Penalty auto-attachment disabled
    # penalty = user.penalty_balance
    # if penalty > 0:
    #     price += int(penalty)
    #     user.penalty_balance = 0
    #     user.save(update_fields=['penalty_balance'])

    # Serializer handles creation of request and stops
    ride_request = serializer.save(
        user=user,
        estimated_price=price,
        estimated_distance=round(distance, 2),
        estimated_duration=max(int(distance * 3), 5) + (len(stops_data) * 3)
    )

    # Semi-automatic dispatch: Notify admin for long trips
    if ride_request.estimated_duration > 5:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "admin_group",
            {
                "type": "admin_notification",
                "notification_type": "long_trip_request",
                "request_id": ride_request.id,
                "duration": ride_request.estimated_duration,
                "message": f"Yangi uzoq masofali buyurtma (#{ride_request.id}). Davomiyligi: {ride_request.estimated_duration} min."
            }
        )

    # Try to find a match (only for non-scheduled or immediately scheduled)
    if not ride_request.is_scheduled:
        match_result = find_match(ride_request)
        if match_result:
            ride_request.refresh_from_db()

    return Response(
        RideRequestSerializer(ride_request).data,
        status=status.HTTP_201_CREATED
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_ride(request, ride_id):
    """Driver accepts a ride request."""
    try:
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        return Response(
            {'detail': 'Safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        driver = request.user.driver_profile
    except Exception:
        return Response(
            {'detail': 'Haydovchi profili topilmadi.'},
            status=status.HTTP_403_FORBIDDEN
        )

    if ride.driver and ride.driver != driver:
        return Response(
            {'detail': 'Bu safar boshqa haydovchiga tayinlangan.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ride.driver = driver
    ride.status = 'driver_found'
    ride.save()

    # Haydovchi qulfini ochish — endi yangi buyurtma qabul qila oladi
    driver.is_being_requested = False
    driver.save(update_fields=['is_being_requested'])

    ride.requests.filter(status='matched').update(status='accepted')
    notify_ride_status_update(ride.id, 'driver_found')

    return Response(RideSerializer(ride).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_ride(request, ride_id):
    """Cancel a ride (by passenger or driver)."""
    try:
        ride = Ride.objects.get(id=ride_id)
    except Ride.DoesNotExist:
        return Response(
            {'detail': 'Safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if ride.status in ['completed', 'cancelled']:
        return Response(
            {'detail': 'Bu safarni bekor qilib bo\'lmaydi.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user

    # If passenger cancelling, remove from ride
    if user.role == 'passenger':
        passenger = ride.passengers.filter(user=user).first()
        if passenger:
            # Cancellation fee disabled
            # if ride.status in ['driver_found', 'on_the_way', 'arrived']:
            #     pricing = get_active_pricing()
            #     fee = pricing.get('cancellation_fee', 2000)
            #     user.penalty_balance += fee
            #     user.save(update_fields=['penalty_balance'])

            passenger.delete()
            RideRequest.objects.filter(
                user=user, ride=ride
            ).update(status='cancelled')

            # If no passengers left, cancel the ride
            if ride.passengers.count() == 0:
                ride.status = 'cancelled'
                ride.save()

        # === ANTI-FRAUD: Ketma-ket bekor qilish nazorati ===
        from django.utils import timezone
        from datetime import timedelta
        from django.conf import settings as conf_settings
        from accounts.models import Wallet

        policy = conf_settings.CANCELLATION_POLICY
        now = timezone.now()
        window = timedelta(hours=policy.get('TIME_WINDOW_HOURS', 1))

        # Check if cancellation is within the window
        if user.last_cancellation_at and (now - user.last_cancellation_at) < window:
            user.cancellation_count += 1
        else:
            user.cancellation_count = 1

        user.last_cancellation_at = now
        
        # JARIMA: ketma-ket 3 marta bekor qilish → 1000 UZS yechiladi + xabar
        if user.cancellation_count >= 3:
            user.cancellation_count = 0

            penalty = Decimal(str(policy.get('PENALTY_STEP_1', 1000)))
            try:
                from accounts.models import Wallet
                wallet, _ = Wallet.objects.get_or_create(user=user)
                wallet.withdraw(penalty, description="Ketma-ket 3 marta bekor qilish jarimasi")
                logger.warning(
                    "Jarima: %s dan %d UZS yechildi (3x bekor qilish)",
                    user.phone, penalty
                )
            except Exception as e:
                logger.error("Jarima yechishda xatolik %s: %s", user.phone, e)

            # Adminni va mijozni xabardor qilish
            try:
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        "admin_group",
                        {
                            "type": "admin_notification",
                            "notification_type": "fraud_alert",
                            "message": (
                                f"⚠️ JARIMA! {user.phone} 3 marta ketma-ket buyurtma bekor qildi. "
                                f"Hisobidan {int(penalty):,} so'm yechildi."
                            ),
                            "user_id": user.id,
                            "user_phone": user.phone,
                        }
                    )
            except Exception as e:
                logger.error("Admin bildirishnomasida xatolik: %s", e)

        user.save(update_fields=['cancellation_count', 'last_cancellation_at'])

    else:
        # Haydovchi bekor qiladi — qulfni ochish
        try:
            driver = request.user.driver_profile
            driver.is_being_requested = False
            driver.save(update_fields=['is_being_requested'])
        except Exception:
            pass

        ride.status = 'cancelled'
        ride.save()
        ride.requests.exclude(status__in=['completed', 'cancelled']).update(
            status='cancelled'
        )

    notify_ride_status_update(ride.id, 'cancelled')

    return Response(RideSerializer(ride).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_ride(request, ride_id):
    """Driver starts the ride."""
    try:
        ride = Ride.objects.get(id=ride_id)
        driver = request.user.driver_profile
    except (Ride.DoesNotExist, Exception):
        return Response(
            {'detail': 'Safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if ride.driver != driver:
        return Response(
            {'detail': 'Bu safar sizga tayinlanmagan.'},
            status=status.HTTP_403_FORBIDDEN
        )

    ride.status = 'started'
    ride.started_at = timezone.now()
    ride.save()

    # Also update requests
    ride.requests.filter(status='accepted').update(status='started')

    notify_ride_status_update(ride.id, 'started')

    return Response(RideSerializer(ride).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_arrived(request, ride_id):
    """Driver marks that they have arrived at the pickup point."""
    try:
        ride = Ride.objects.get(id=ride_id)
        driver = request.user.driver_profile
    except (Ride.DoesNotExist, Exception):
        return Response(
            {'detail': 'Safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if ride.driver != driver:
        return Response(
            {'detail': 'Bu safar sizga tayinlanmagan.'},
            status=status.HTTP_403_FORBIDDEN
        )

    ride.status = 'arrived'
    ride.save()
    
    # Update current passengers arrival time
    ride.passengers.filter(picked_up=False).update(arrived_at=timezone.now())
    # Update requests status for passenger UI
    ride.requests.filter(status='accepted').update(status='arrived')

    notify_ride_status_update(ride.id, 'arrived')

    return Response(RideSerializer(ride).data)


def _finalize_ride(ride, driver):
    """Safar yakunlash: komissiya, keshbek, referral bonus, maqsad."""
    from pricing.engine import recalculate_ride_fares
    from accounts.models import Wallet
    from accounts.cashback import (
        get_driver_commission_rate,
        apply_passenger_cashback,
        queue_referral_bonus,
        is_bonus_usable,
        check_and_complete_driver_goal,
        MAX_BONUS_USAGE,
    )

    ride.status = 'completed'
    ride.completed_at = timezone.now()

    # Haydovchi komissiya stavkasini hisoblash (intro / happy hours / goal discount)
    commission_rate = get_driver_commission_rate(driver)
    ride.commission_rate = commission_rate

    total = recalculate_ride_fares(ride)
    is_shared = ride.passengers.count() > 1

    from pricing.engine import calculate_commission
    ride.commission_amount = calculate_commission(total, is_shared=is_shared)
    ride.driver_earnings = total - ride.commission_amount
    ride.save()

    driver_wallet, _ = Wallet.objects.get_or_create(user=driver.user)
    driver_wallet.deposit(ride.driver_earnings, f"Safar #{ride.id} daromadi")

    for passenger in ride.passengers.all():
        pass_wallet, _ = Wallet.objects.get_or_create(user=passenger.user)
        user = passenger.user
        fare = Decimal(str(passenger.fare))
        req = passenger.ride_request
        payment_method = getattr(req, 'payment_method', 'cash') if req else 'cash'
        bonus_usage = Decimal('0')

        # Bonus ishlatish (faqat 6-safardan keyin)
        if req and req.use_bonus and user.bonus_balance > 0 and is_bonus_usable(user):
            max_bonus = fare * MAX_BONUS_USAGE
            intent = Decimal(str(req.bonus_percent)) / Decimal('100')
            target = max_bonus * intent
            bonus_usage = min(user.bonus_balance, target)
            from decimal import ROUND_HALF_UP
            bonus_usage = bonus_usage.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            user.bonus_balance -= bonus_usage
            user.save(update_fields=['bonus_balance'])
        elif req and req.use_bonus and not is_bonus_usable(user):
            # Hali 6-safardan o'tmagan — bonusni bloklash
            from rides.utils import notify_ride_status_update as _n
            pass  # Frontend xabar beradi

        remaining_fare = fare - bonus_usage
        if remaining_fare > 0:
            pass_wallet.withdraw(
                remaining_fare,
                description=f"Safar #{ride.id} to'lovi (bonus: {int(bonus_usage)} UZS)"
            )

        # GoldPoints: har 1000 UZS uchun 1 ball
        points = int(fare / 1000)
        if points > 0:
            user.add_gold_points(points)

        # Yo'lovchiga keshbek (kirish davri yoki doimiy)
        apply_passenger_cashback(user, fare, payment_method)

        # Mijoz safarlar soni +1
        user.total_passenger_rides = (user.total_passenger_rides or 0) + 1
        user.save(update_fields=['total_passenger_rides'])

        # Referral bonus (ertaga tushadi)
        if user.referred_by:
            queue_referral_bonus(
                referrer=user.referred_by,
                passenger=user,
                fare=fare,
                payment_method=payment_method,
            )
            user.referral_rides_count = (user.referral_rides_count or 0) + 1
            user.save(update_fields=['referral_rides_count'])

    # Haydovchi statistikasi yangilash
    driver.commission_paid = (driver.commission_paid or Decimal('0')) + ride.commission_amount
    driver.total_earnings = (driver.total_earnings or Decimal('0')) + ride.total_price
    driver.total_rides = (driver.total_rides or 0) + 1
    driver.total_rides_completed = (driver.total_rides_completed or 0) + 1
    driver.save(update_fields=[
        'commission_paid', 'total_earnings', 'total_rides',
        'total_rides_completed', 'intro_period_completed',
    ])

    # Haydovchi maqsad taraqqiyoti tekshiruvi
    check_and_complete_driver_goal(driver, ride)

    ride.passengers.filter(dropped_off=False).update(dropped_off=True, dropped_off_at=timezone.now())
    ride.requests.filter(status__in=['accepted', 'arrived', 'started']).update(status='completed')
    notify_ride_status_update(ride.id, 'completed')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_ride(request, ride_id):
    """Driver completes the ride."""
    try:
        ride = Ride.objects.get(id=ride_id)
        driver = request.user.driver_profile
    except (Ride.DoesNotExist, Exception):
        return Response({'detail': 'Safar topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

    if ride.driver != driver:
        return Response({'detail': 'Bu safar sizga tayinlanmagan.'}, status=status.HTTP_403_FORBIDDEN)

    _finalize_ride(ride, driver)
    return Response(RideSerializer(ride).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pickup_passenger(request, ride_id, passenger_id):
    """Mark a passenger as picked up."""
    try:
        passenger = RidePassenger.objects.get(ride_id=ride_id, id=passenger_id)
    except RidePassenger.DoesNotExist:
        return Response(
            {'detail': 'Yo\'lovchi topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    passenger.picked_up = True
    passenger.picked_up_at = timezone.now()
    
    # Calculate waiting penalty
    if passenger.arrived_at:
        wait_time = passenger.picked_up_at - passenger.arrived_at
        wait_minutes = wait_time.total_seconds() / 60
        # Waiting penalty disabled
        # if wait_minutes > 2:
        #     pricing = get_active_pricing()
        #     penalty = int(wait_minutes - 2) * pricing.get('waiting_rate_per_min', 500)
        #     passenger.waiting_penalty = penalty
        #     passenger.fare += penalty
            
    passenger.save()

    # If all passengers picked up, update ride status
    ride = passenger.ride
    if not ride.passengers.filter(picked_up=False).exists():
        ride.status = 'started'
        ride.started_at = timezone.now()
        ride.save()
        notify_ride_status_update(ride.id, 'started')
    else:
        # Just notify about the specific passenger being picked up
        notify_ride_status_update(ride.id, 'passenger_picked_up')

    return Response({'status': 'ok', 'picked_up': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dropoff_passenger(request, ride_id, passenger_id):
    """Mark a passenger as dropped off."""
    try:
        passenger = RidePassenger.objects.get(ride_id=ride_id, id=passenger_id)
    except RidePassenger.DoesNotExist:
        return Response(
            {'detail': 'Yo\'lovchi topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    passenger.dropped_off = True
    passenger.dropped_off_at = timezone.now()
    passenger.save()

    ride = passenger.ride

    # If all passengers dropped off, complete the ride
    if not ride.passengers.filter(dropped_off=False).exists():
        try:
            driver = request.user.driver_profile
        except Exception:
            return Response({'detail': 'Haydovchi profili topilmadi.'}, status=status.HTTP_403_FORBIDDEN)
        _finalize_ride(ride, driver)
        return Response(RideSerializer(ride).data)

    notify_ride_status_update(ride.id, 'passenger_dropped_off')
    return Response({'status': 'ok', 'dropped_off': True})


class RideHistoryView(generics.ListAPIView):
    """Ride history for current user (as passenger or driver)."""
    serializer_class = RideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'driver' and hasattr(user, 'driver_profile'):
            return Ride.objects.filter(driver=user.driver_profile)
        return Ride.objects.filter(passengers__user=user).distinct()


class DriverActiveRidesView(generics.ListAPIView):
    """Active rides for the current driver."""
    serializer_class = RideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        driver = self.request.user.driver_profile
        return Ride.objects.filter(
            driver=driver,
            status__in=['searching', 'driver_found', 'on_the_way', 'started']
        )


class DriverEarningsView(generics.ListAPIView):
    """Completed rides for earnings tracking."""
    serializer_class = RideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        driver = self.request.user.driver_profile
        return Ride.objects.filter(
            driver=driver,
            status='completed'
        ).order_by('-completed_at')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rate_ride(request, ride_id):
    """Rate a completed ride."""
    serializer = RideRatingSerializer(data={
        **request.data,
        'ride': ride_id
    })
    serializer.is_valid(raise_exception=True)

    try:
        ride = Ride.objects.get(id=ride_id, status='completed')
    except Ride.DoesNotExist:
        return Response(
            {'detail': 'Yakunlangan safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Determine target user
    target_user_id = request.data.get('target_user_id')
    target_user = None
    
    if request.user.role == 'driver':
        if not target_user_id:
            return Response({'detail': 'Yo\'lovchi ID si ko\'rsatilmadi.'}, status=400)
        try:
            from accounts.models import User
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({'detail': 'Yo\'lovchi topilmadi.'}, status=404)
    else:
        if ride.driver:
            target_user = ride.driver.user
            
    if not target_user:
        return Response({'detail': 'Baho beriladigan foydalanuvchi topilmadi.'}, status=400)

    rating = RideRating.objects.create(
        ride=ride,
        user=request.user,
        target_user=target_user,
        rating=serializer.validated_data['rating'],
        comment=serializer.validated_data.get('comment', '')
    )

    # Update average rating for the target user
    all_ratings = RideRating.objects.filter(target_user=target_user)
    avg = all_ratings.aggregate(Avg('rating'))['rating__avg']
    
    if avg:
        avg = round(avg, 2)
        if hasattr(target_user, 'driver_profile') and target_user.role == 'driver':
            driver = target_user.driver_profile
            driver.rating = avg
            driver.save(update_fields=['rating'])
        else:
            # Update passenger rating on User model
            target_user.passenger_rating = avg
            target_user.save(update_fields=['passenger_rating'])

    return Response(RideRatingSerializer(rating).data, status=status.HTTP_201_CREATED)


class AdminDashboardStatsView(APIView):
    """View to provide aggregated stats for the admin dashboard."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        User = get_user_model()
        now = timezone.now()
        last_24h = now - timedelta(days=1)

        # Basic Stats
        total_rides = Ride.objects.count()
        new_users = User.objects.filter(created_at__gte=last_24h).count()
        
        revenue_data = Ride.objects.filter(status='completed').aggregate(
            total=Sum('total_price')
        )
        total_revenue = float(revenue_data['total'] or 0)

        # Average ride time in minutes
        avg_time_data = Ride.objects.filter(
            status='completed', 
            started_at__isnull=False, 
            completed_at__isnull=False
        ).annotate(
            duration=F('completed_at') - F('started_at')
        ).aggregate(avg_duration=Avg('duration'))
        
        avg_time = 0
        if avg_time_data['avg_duration']:
            avg_time = int(avg_time_data['avg_duration'].total_seconds() / 60)

        # Chart Data (last 7 days)
        chart_data = []
        for i in range(6, -1, -1):
            date = (now - timedelta(days=i)).date()
            day_rides = Ride.objects.filter(created_at__date=date).count()
            day_revenue = Ride.objects.filter(
                created_at__date=date, 
                status='completed'
            ).aggregate(total=Sum('total_price'))['total'] or 0
            
            chart_data.append({
                'name': date.strftime('%a'),
                'rides': day_rides,
                'revenue': float(day_revenue)
            })

        # Recent Rides
        recent_rides = Ride.objects.select_related('driver__user').prefetch_related('passengers__user')[:5]
        recent_data = []
        for ride in recent_rides:
            first_p = ride.passengers.first()
            recent_data.append({
                'id': ride.id,
                'user': (first_p.user.get_full_name() or first_p.user.phone) if first_p else 'Noma\'lum',
                'user_phone': first_p.user.phone if first_p else '',
                'driver': ride.driver.user.get_full_name() if (ride.driver and ride.driver.user) else 'Qidirilmoqda',
                'price': float(ride.total_price),
                'status': ride.status,
                'status_display': ride.get_status_display()
            })

        return Response({
            'stats': [
                { 'title': 'Jami Safarlar', 'value': f'{total_rides:,}', 'change': '+0%', 'isUp': True },
                { 'title': 'Yangi Foydalanuvchilar', 'value': f'{new_users}', 'change': '+0%', 'isUp': True },
                { 'title': 'Jami Daromad', 'value': f'{total_revenue:,.0f} UZS', 'change': '+0%', 'isUp': True },
                { 'title': 'O\'rtacha vaqt', 'value': f'{avg_time} min', 'change': '+0%', 'isUp': True },
            ],
            'chart_data': chart_data,
            'recent_rides': recent_data
        })


class AdminRideListView(APIView):
    """Admin-only: List all rides and pending requests in the system."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        try:
            # All rides (active and past)
            rides = Ride.objects.all().select_related('driver__user').prefetch_related('passengers__user').order_by('-created_at')[:100]
            
            # Pending, Matched, or External requests (Still being processed)
            pending_requests = RideRequest.objects.filter(
                status__in=['pending', 'matched', 'external_pending', 'accepted']
            ).select_related('user').order_by('-created_at')[:50]

            print(f"[AdminAPI] GET Rides - Found {rides.count()} rides and {pending_requests.count()} pending requests.")

            rides_data = RideSerializer(rides, many=True).data
            pending_data = RideRequestSerializer(pending_requests, many=True).data

            print(f"[AdminAPI] Serialized {len(rides_data)} rides and {len(pending_data)} pending requests.")

            return Response({
                'rides': rides_data,
                'pending_requests': pending_data
            })
        except Exception as e:
            print(f"[AdminAPI] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'detail': str(e)}, status=500)


class AdminAnalyticsView(APIView):
    """Admin-only: Deeper analytics for revenue and ride volume."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        User = get_user_model()
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # Revenue Breakdown
        completed_rides = Ride.objects.filter(status='completed', created_at__gte=thirty_days_ago)
        shared_revenue = completed_rides.filter(is_shared=True).aggregate(Sum('total_price'))['total_price__sum'] or 0
        regular_revenue = completed_rides.filter(is_shared=False).aggregate(Sum('total_price'))['total_price__sum'] or 0

        # Ride Counts
        shared_count = completed_rides.filter(is_shared=True).count()
        regular_count = completed_rides.filter(is_shared=False).count()

        # Growth Data (last 30 days daily)
        growth_data = []
        for i in range(29, -1, -1):
            date = (now - timedelta(days=i)).date()
            day_rides = Ride.objects.filter(created_at__date=date).count()
            day_users = User.objects.filter(created_at__date=date).count()
            
            growth_data.append({
                'date': date.strftime('%d-%b'),
                'rides': day_rides,
                'users': day_users
            })

        return Response({
            'overview': {
                'shared_revenue': float(shared_revenue),
                'regular_revenue': float(regular_revenue),
                'shared_count': shared_count,
                'regular_count': regular_count,
                'total_revenue': float(shared_revenue + regular_revenue)
            },
            'growth_data': growth_data
        })


class RideRequestStatusView(generics.RetrieveAPIView):
    """Passenger polls this to see if their request is accepted."""
    serializer_class = RideRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RideRequest.objects.filter(user=self.request.user)


class PassengerActiveRequestView(APIView):
    """Get the active ride request for the current passenger."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            req = RideRequest.objects.get(
                user=request.user,
                status__in=['pending', 'matched', 'accepted']
            )
            serializer = RideRequestSerializer(req)
            return Response({
                'active': True,
                'request': serializer.data
            })
        except RideRequest.DoesNotExist:
            return Response({
                'active': False,
                'detail': "No active ride request found."
            })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite_driver(request, driver_id):
    """Add or remove a driver from favorites."""
    try:
        driver = Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        return Response({'detail': 'Haydovchi topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

    favorite, created = FavoriteDriver.objects.get_or_create(
        user=request.user,
        driver=driver
    )
    
    if not created:
        favorite.delete()
        return Response({'status': 'removed', 'is_favorite': False})
    
    return Response({'status': 'added', 'is_favorite': True}, status=status.HTTP_201_CREATED)


class FavoriteDriversListView(generics.ListAPIView):
    """List current user's favorite drivers."""
    serializer_class = DriverProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Driver.objects.filter(favorited_by__user=self.request.user)


class ChatMessageListCreateView(generics.ListCreateAPIView):
    """List and send chat messages for a ride."""
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ride_id = self.kwargs.get('ride_id')
        return ChatMessage.objects.filter(ride_id=ride_id)

    def perform_create(self, serializer):
        ride_id = self.kwargs.get('ride_id')
        serializer.save(ride_id=ride_id, sender=self.request.user)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_dispatch_external(request, request_id):
    """Admin marks a request as being handled by an external provider."""
    if request.user.role != 'admin' and not request.user.is_staff:
        return Response({'detail': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        ride_req = RideRequest.objects.get(id=request_id)
    except RideRequest.DoesNotExist:
        return Response({'detail': 'So\'rov topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
    
    provider = request.data.get('provider') # Yandex, Fasten, etc.
    order_id = request.data.get('external_order_id')
    external_price = request.data.get('external_price')
    eta_minutes = request.data.get('eta_minutes')  # How many minutes until driver arrives
    
    if not provider:
        return Response({'detail': 'Provayder ko\'rsatilmadi.'}, status=status.HTTP_400_BAD_REQUEST)
    
    ride_req.status = 'external_pending'
    ride_req.external_provider = provider
    ride_req.external_order_id = order_id
    
    if external_price:
        ride_req.estimated_price = external_price
    
    if eta_minutes:
        ride_req.external_eta = timezone.now() + timedelta(minutes=int(eta_minutes))
        
    ride_req.save()
    
    # Notify user via WebSocket about the update
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"ride_{ride_req.id}",
        {
            "type": "ride_status_update",
            "ride_id": ride_req.id,
            "status": "external_pending",
            "provider": provider,
            "eta_minutes": int(eta_minutes) if eta_minutes else None,
            "new_price": float(ride_req.estimated_price) if external_price else None
        }
    )
    
    return Response(RideRequestSerializer(ride_req).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_external_arrived(request, request_id):
    """Admin marks that the external driver has arrived at the pickup."""
    if request.user.role != 'admin' and not request.user.is_staff:
        return Response({'detail': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        ride_req = RideRequest.objects.get(id=request_id)
    except RideRequest.DoesNotExist:
        return Response({'detail': 'So\'rov topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
    
    if ride_req.status != 'external_pending':
        return Response({'detail': 'Bu so\'rov tashqi xizmatda emas.'}, status=status.HTTP_400_BAD_REQUEST)
    
    ride_req.status = 'completed'
    ride_req.save()
    
    # Notify user via WebSocket
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"ride_{ride_req.id}",
        {
            "type": "ride_status_update",
            "ride_id": ride_req.id,
            "status": "external_arrived",
            "provider": ride_req.external_provider,
            "message": f"{ride_req.external_provider} haydovchisi yetib keldi!"
        }
    )
    
    return Response(RideRequestSerializer(ride_req).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_update_external_eta(request, request_id):
    """Admin updates the ETA for an external dispatch."""
    if request.user.role != 'admin' and not request.user.is_staff:
        return Response({'detail': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        ride_req = RideRequest.objects.get(id=request_id)
    except RideRequest.DoesNotExist:
        return Response({'detail': 'So\'rov topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
    
    eta_minutes = request.data.get('eta_minutes')
    if not eta_minutes:
        return Response({'detail': 'Vaqt ko\'rsatilmadi.'}, status=status.HTTP_400_BAD_REQUEST)
    
    ride_req.external_eta = timezone.now() + timedelta(minutes=int(eta_minutes))
    ride_req.save()
    
    # Notify user via WebSocket
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"ride_{ride_req.id}",
        {
            "type": "ride_status_update",
            "ride_id": ride_req.id,
            "status": "external_pending",
            "eta_minutes": int(eta_minutes),
            "message": f"Haydovchi taxminan {eta_minutes} daqiqada yetib keladi"
        }
    )
    
    return Response(RideRequestSerializer(ride_req).data)


class AdminAnalyticsView(generics.GenericAPIView):
    """Analytics and Heatmap data for Admin."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        # Demand Heatmap (Recent pending/matched requests)
        recent_cutoff = timezone.now() - timedelta(hours=2)
        requests = RideRequest.objects.filter(
            created_at__gte=recent_cutoff,
            status__in=['pending', 'matched']
        ).values('pickup_lat', 'pickup_lng')
        
        heatmap_data = []
        for r in requests:
            heatmap_data.append({
                'latitude': r['pickup_lat'],
                'longitude': r['pickup_lng'],
                'weight': 1.0
            })

        # Supply stats
        online_drivers = Driver.objects.filter(is_online=True).count()
        active_rides = Ride.objects.filter(status__in=['driver_found', 'on_the_way', 'arrived', 'started']).count()

        return Response({
            'heatmap': heatmap_data,
            'stats': {
                'online_drivers': online_drivers,
                'active_rides': active_rides,
                'pending_requests': RideRequest.objects.filter(status='pending').count(),
            }
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_sos(request):
    """Trigger an emergency alert (SOS)."""
    lat = request.data.get('latitude')
    lng = request.data.get('longitude')
    ride_id = request.data.get('ride_id')

    if not lat or not lng:
        return Response(
            {'detail': 'Joylashuv ma\'lumotlari zarur.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ride = None
    if ride_id:
        try:
            ride = Ride.objects.get(id=ride_id)
        except Ride.DoesNotExist:
            pass

    alert = EmergencyAlert.objects.create(
        user=request.user,
        ride=ride,
        latitude=lat,
        longitude=lng
    )

    # TODO: Send SMS to admin or emergency contacts
    
    return Response({
        'detail': 'SOS signali yuborildi. Yordam yo\'lda.',
        'alert_id': alert.id
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_history(request, ride_id):
    """Get chat history for a ride."""
    try:
        ride = Ride.objects.get(id=ride_id)
        # Check if user is part of the ride
        is_passenger = ride.passengers.filter(user=request.user).exists()
        is_driver = (ride.driver and ride.driver.user == request.user)
        
        if not is_passenger and not is_driver:
            return Response(
                {'detail': 'Siz ushbu safar chatini ko\'rish huquqiga ega emassiz.'},
                status=status.HTTP_403_FORBIDDEN
            )
            
        messages = ride.chat_messages.all()
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)
    except Ride.DoesNotExist:
        return Response(
            {'detail': 'Safar topilmadi.'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_daily_report(request):
    """Daily summary for drivers."""
    try:
        driver = request.user.driver_profile
    except Exception:
        return Response({'detail': 'Haydovchi profili topilmadi.'}, status=403)

    today = timezone.now().date()
    rides = Ride.objects.filter(
        driver=driver,
        status='completed',
        completed_at__date=today
    )
    
    stats = rides.aggregate(
        total_rides=Count('id'),
        total_earnings=Sum('driver_earnings'),
        total_distance=Sum('total_distance')
    )
    
    return Response({
        'date': today,
        'total_rides': stats['total_rides'] or 0,
        'total_earnings': stats['total_earnings'] or 0,
        'total_distance': round(stats['total_distance'] or 0, 2),
        'currency': 'UZS'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_transaction_logs(request):
    """Transaction logs for users (wallet history)."""
    from accounts.models import Wallet, WalletTransaction
    from accounts.serializers import WalletTransactionSerializer
    
    try:
        wallet = request.user.wallet
    except Wallet.DoesNotExist:
        return Response({'transactions': []})
        
    transactions = WalletTransaction.objects.filter(
        wallet=wallet
    ).order_by('-created_at')[:50]
    
    return Response({
        'balance': wallet.balance,
        'gold_points': request.user.gold_points,
        'transactions': WalletTransactionSerializer(transactions, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_happy_hours(request):
    """Return current happy hour status and schedule."""
    from django.conf import settings as conf_settings
    
    now_local = timezone.localtime(timezone.now())
    current_time_str = now_local.strftime('%H:%M')
    default_rate = conf_settings.PRICING.get('COMMISSION_RATE', 0.05)
    
    current_happy_hour = None
    for hh in conf_settings.HAPPY_HOURS:
        if hh['start'] <= current_time_str < hh['end']:
            current_happy_hour = hh
            break
    
    return Response({
        'is_active': current_happy_hour is not None,
        'current': {
            'start': current_happy_hour['start'],
            'end': current_happy_hour['end'],
            'commission_rate': current_happy_hour['commission_rate'],
            'label': current_happy_hour['label'],
            'min_fare': current_happy_hour.get('min_fare', 5000),
            'multi_stop_fee': current_happy_hour.get('multi_stop_fee', 2000),
            'scheduled_fee': current_happy_hour.get('scheduled_fee', 5000),
            'cancellation_fee': current_happy_hour.get('cancellation_fee', 2000),
            'waiting_rate_per_min': current_happy_hour.get('waiting_rate_per_min', 500),
            'discount_percent': int((1 - current_happy_hour['commission_rate'] / default_rate) * 100),
        } if current_happy_hour else None,
        'default_commission_rate': default_rate,
        'schedule': [
            {
                'start': hh['start'],
                'end': hh['end'],
                'commission_rate': hh['commission_rate'],
                'label': hh['label'],
                'min_fare': hh.get('min_fare', 5000),
                'multi_stop_fee': hh.get('multi_stop_fee', 2000),
                'scheduled_fee': hh.get('scheduled_fee', 5000),
                'cancellation_fee': hh.get('cancellation_fee', 2000),
                'waiting_rate_per_min': hh.get('waiting_rate_per_min', 500),
                'discount_percent': int((1 - hh['commission_rate'] / default_rate) * 100),
            }
            for hh in conf_settings.HAPPY_HOURS
        ],
        'server_time': current_time_str,
    })

# --- ADMIN RIDE MANAGEMENT ---

class AdminRideDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin: Get, update or delete a ride."""
    queryset = Ride.objects.all()
    serializer_class = RideSerializer
    permission_classes = [IsAdminUser]

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_complete_ride(request, pk):
    """Admin: Force complete a ride."""
    try:
        ride = Ride.objects.get(pk=pk)
    except Ride.DoesNotExist:
        return Response({'detail': 'Safar topilmadi.'}, status=404)
    
    if ride.status == 'completed':
        return Response({'detail': 'Safar allaqachon yakunlangan.'})

    ride.status = 'completed'
    ride.completed_at = timezone.now()
    ride.save()
    
    # Notify involved parties
    from .utils import notify_ride_status_update
    notify_ride_status_update(ride.id, 'completed')
    
    return Response({'status': 'ok', 'message': 'Safar admin tomonidan yakunlandi.'})

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_cancel_ride(request, pk):
    """Admin: Force cancel a ride."""
    try:
        ride = Ride.objects.get(pk=pk)
        ride.status = 'cancelled'
        ride.save()
        ride.requests.exclude(status__in=['completed', 'cancelled']).update(status='cancelled')
        from .utils import notify_ride_status_update
        notify_ride_status_update(ride.id, 'cancelled')
        return Response({'status': 'ok', 'message': 'Safar bekor qilindi.'})
    except Ride.DoesNotExist:
        return Response({'detail': 'Safar topilmadi.'}, status=404)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_cancel_request(request, pk):
    """Admin: Force cancel a ride request."""
    try:
        ride_req = RideRequest.objects.get(pk=pk)
        ride_req.status = 'cancelled'
        ride_req.save()
        
        # Notify passenger
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{ride_req.user.id}",
            {
                "type": "ride_status_update",
                "request_id": ride_req.id,
                "status": "cancelled",
                "message": "Sizning buyurtmangiz administrator tomonidan bekor qilindi."
            }
        )
        return Response({'status': 'ok', 'message': 'So\'rov bekor qilindi.'})
    except RideRequest.DoesNotExist:
        return Response({'detail': 'So\'rov topilmadi.'}, status=404)

class AdminRideRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin: Get, update or delete a ride request."""
    queryset = RideRequest.objects.all()
    serializer_class = RideRequestSerializer
    permission_classes = [IsAdminUser]
