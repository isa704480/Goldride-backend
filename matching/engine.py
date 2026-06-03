"""
Matching Engine — Yo'lovchilarni haydovchilar bilan moslashtirish algoritmi.

Mantiq:
1. SEARCH_RADIUS_KM ichidagi onlayn haydovchilarni topish
2. Mavjud hamrohlik safariga qo'shib bo'ladimi — tekshirish
3. Yo'nalish og'ishi MAX_ROUTE_DEVIATION dan kam bo'lsa — qo'shish
4. Aks holda — eng yaxshi bo'sh haydovchiga yangi safar yaratish

Haydovchi reytingi = rating * 0.35 + (1/ETA) * 0.40 + acceptance_rate * 0.25
"""

import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from accounts.models import Driver
from rides.models import Ride, RideRequest, RidePassenger
from pricing.engine import haversine, calculate_price, calculate_distance, AVG_SPEED_KMH
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger('matching')


def notify_driver_new_ride(driver, ride):
    """Haydovchiga WebSocket orqali yangi safar so'rovi yuborish."""
    from rides.serializers import RideSerializer

    logger.info("Haydovchiga safar #%d yuborilmoqda: %s", ride.id, driver.user.phone)
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{driver.user.id}',
            {
                'type': 'ride_request',
                'ride': RideSerializer(ride).data,
            }
        )
        logger.info("Muvaffaqiyatli yuborildi: haydovchi %s", driver.user.phone)
    except Exception as e:
        logger.error("Haydovchiga yuborishda xatolik %s: %s", driver.user.phone, e, exc_info=True)


def _get_acceptance_rate(driver):
    """Haydovchining so'rovlarni qabul qilish foizini hisoblash (0.0 – 1.0)."""
    total = getattr(driver, 'total_requests_received', 0)
    accepted = getattr(driver, 'total_rides_completed', 0)
    if total > 0:
        return min(1.0, accepted / total)
    return 0.75  # Ma'lumot yo'q bo'lsa o'rtacha qiymat


def _ranking_score(driver, passenger_lat, passenger_lng, radius_km):
    """
    Haydovchi reytingi formulasi:
      score = rating * 0.35  +  (1/ETA_min) * 0.40  +  acceptance_rate * 0.25

    ETA_min = masofa / o'rtacha tezlik * 60
    Katta score — yaxshiroq haydovchi.
    """
    dist_km = haversine(passenger_lat, passenger_lng, driver.current_lat, driver.current_lng)
    eta_min = max(0.5, (dist_km / AVG_SPEED_KMH) * 60)

    rating = float(driver.rating or 4.5)
    acceptance = _get_acceptance_rate(driver)

    score = (rating * 0.35) + ((1.0 / eta_min) * 0.40) + (acceptance * 0.25)
    return score


def get_nearby_drivers(lat, lng, radius_km=None, requested_category='economy'):
    """
    Radius ichidagi onlayn, tasdiqlangan, minimal balansga ega haydovchilarni topish.
    Qaytarish tartibi: eng yaxshi score birinchi.
    """
    if radius_km is None:
        radius_km = settings.MATCHING['SEARCH_RADIUS_KM']

    category = requested_category
    if category == 'start':
        category = 'economy'

    hierarchy = ['economy', 'comfort', 'electro', 'business']
    try:
        idx = hierarchy.index(category)
        eligible_classes = hierarchy[idx:]
    except ValueError:
        eligible_classes = [category]

    drivers_qs = Driver.objects.filter(
        is_online=True,
        status='approved',
        current_lat__isnull=False,
        current_lng__isnull=False,
        vehicle__car_class__in=eligible_classes,
        is_being_requested=False,  # Hozir boshqa so'rov kutayotgan haydovchilar chiqarib tashlanadi
    ).select_related('user', 'vehicle', 'user__wallet')

    bal_cfg = settings.DRIVER_BALANCE
    first_month_days = bal_cfg.get('FIRST_MONTH_DAYS', 30)
    now = timezone.now()

    nearby = []
    for driver in drivers_qs:
        dist = haversine(lat, lng, driver.current_lat, driver.current_lng)
        if dist > radius_km:
            continue

        # Minimal balans tekshiruvi
        try:
            from accounts.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=driver.user)
            balance = wallet.balance

            days_joined = (now - driver.created_at).days
            if days_joined <= first_month_days:
                min_bal = bal_cfg.get('FIRST_MONTH_MINIMUM', 40000)
            else:
                min_bal = bal_cfg.get('AFTER_MONTH_MINIMUM', 20000)

            if balance < min_bal:
                logger.debug(
                    "Haydovchi %s o'tkazib yuborildi (balans: %s < %s)",
                    driver.user.phone, balance, min_bal
                )
                continue
        except Exception as e:
            logger.warning("Balans tekshirishda xatolik %s: %s", driver.user.phone, e)
            continue

        nearby.append(driver)

    nearby.sort(key=lambda d: _ranking_score(d, lat, lng, radius_km), reverse=True)

    results = [(d, haversine(lat, lng, d.current_lat, d.current_lng)) for d in nearby]
    logger.info(
        "Topilgan haydovchilar: %d ta (%s kategoriyasi, radius %.1f km)",
        len(results), requested_category, radius_km
    )
    return results


def calculate_route_deviation(existing_ride, new_request):
    """
    Yangi yo'lovchi qo'shilganda marshrut qanchalik o'zgarishini hisoblash.
    Qaytarish: og'ish nisbati (0.0 = bir xil yo'nalish, 1.0 = teskari).
    """
    existing_passengers = existing_ride.passengers.all()
    if not existing_passengers:
        return 0.0

    avg_drop_lat = sum(p.drop_lat for p in existing_passengers) / len(existing_passengers)
    avg_drop_lng = sum(p.drop_lng for p in existing_passengers) / len(existing_passengers)

    driver = existing_ride.driver
    origin_lat = driver.current_lat
    origin_lng = driver.current_lng

    existing_dist = haversine(origin_lat, origin_lng, avg_drop_lat, avg_drop_lng)
    new_pickup_detour = haversine(origin_lat, origin_lng, new_request.pickup_lat, new_request.pickup_lng)
    new_drop_dist = haversine(new_request.pickup_lat, new_request.pickup_lng, new_request.drop_lat, new_request.drop_lng)
    combined_dist = new_pickup_detour + new_drop_dist

    if existing_dist == 0:
        return 1.0

    deviation = abs(combined_dist - existing_dist) / existing_dist
    return min(deviation, 1.0)


def check_direction_similarity(ride, request):
    """
    Yangi so'rov mavjud safar bilan bir yo'nalishda ekanligini tekshirish.
    Vektorlar orasidagi burchak kosinus orqali: > 0.5 (< 60°) bo'lsa muvofiq.
    """
    passengers = ride.passengers.all()
    if not passengers:
        return True

    driver = ride.driver
    avg_drop_lat = sum(p.drop_lat for p in passengers) / len(passengers)
    avg_drop_lng = sum(p.drop_lng for p in passengers) / len(passengers)

    dir1_lat = avg_drop_lat - driver.current_lat
    dir1_lng = avg_drop_lng - driver.current_lng
    dir2_lat = request.drop_lat - request.pickup_lat
    dir2_lng = request.drop_lng - request.pickup_lng

    dot = dir1_lat * dir2_lat + dir1_lng * dir2_lng
    mag1 = (dir1_lat ** 2 + dir1_lng ** 2) ** 0.5
    mag2 = (dir2_lat ** 2 + dir2_lng ** 2) ** 0.5

    if mag1 == 0 or mag2 == 0:
        return True

    cos_angle = dot / (mag1 * mag2)
    return cos_angle > 0.5


def find_match(ride_request):
    """
    Asosiy moslashtirish funksiyasi.

    1. Yaqin haydovchilarni topish
    2. Mavjud hamrohlik safariga qo'shishga urinish
    3. Imkon bo'lmasa — yangi safar yaratish
    """
    max_passengers = settings.PRICING.get('MAX_PASSENGERS_PER_RIDE', 2)
    max_deviation = settings.MATCHING.get('MAX_ROUTE_DEVIATION', 0.20)
    time_window = settings.MATCHING.get('MATCH_TIME_WINDOW_MINUTES', 5)

    nearby_drivers = get_nearby_drivers(
        ride_request.pickup_lat,
        ride_request.pickup_lng,
        requested_category=ride_request.car_category,
    )

    if not nearby_drivers:
        logger.info("Safar #%d uchun haydovchi topilmadi", ride_request.id)
        return None

    # 1-qadam: Mavjud hamrohlik safariga qo'shish
    if ride_request.is_shared:
        for driver, distance in nearby_drivers:
            active_rides = Ride.objects.filter(
                driver=driver,
                is_shared=True,
                status__in=['searching', 'driver_found', 'on_the_way'],
                created_at__gte=timezone.now() - timedelta(minutes=time_window * 3),
            ).prefetch_related('passengers')

            for ride in active_rides:
                if ride.passengers.count() >= max_passengers:
                    continue
                if calculate_route_deviation(ride, ride_request) > max_deviation:
                    continue
                if not check_direction_similarity(ride, ride_request):
                    continue

                logger.info(
                    "Safar #%d mavjud safar #%d ga qo'shildi (haydovchi: %s)",
                    ride_request.id, ride.id, driver.user.phone
                )
                return add_to_existing_ride(ride, ride_request)

    # 2-qadam: Yangi safar yaratish — haydovchini atomik lock bilan egallash
    for driver, distance in nearby_drivers:
        result = _try_assign_driver(driver, ride_request, max_passengers, max_deviation)
        if result:
            return result

    logger.info("Safar #%d uchun mos haydovchi topilmadi", ride_request.id)
    return None


def _try_assign_driver(driver, ride_request, max_passengers, max_deviation):
    """
    Haydovchini atomik tarzda egallash.
    Race condition oldini olish uchun select_for_update ishlatiladi.
    """
    with transaction.atomic():
        # Haydovchini qulflaymiz (boshqa tranzaksiya o'zgartira olmasin)
        locked_driver = Driver.objects.select_for_update(nowait=True).filter(
            pk=driver.pk,
            is_online=True,
            status='approved',
            is_being_requested=False,
        ).first()

        if not locked_driver:
            return None

        has_active = Ride.objects.filter(
            driver=locked_driver,
            status__in=['searching', 'driver_found', 'on_the_way', 'started'],
        ).exists()

        if has_active and not ride_request.is_shared:
            return None

        if has_active:
            active_ride = Ride.objects.filter(
                driver=locked_driver,
                status__in=['searching', 'driver_found', 'on_the_way'],
                is_shared=True,
            ).prefetch_related('passengers').first()

            if active_ride and active_ride.passengers.count() < max_passengers:
                if calculate_route_deviation(active_ride, ride_request) <= max_deviation:
                    return add_to_existing_ride(active_ride, ride_request)
            return None

        # Haydovchini band qilish (boshqa so'rov kelmasin)
        locked_driver.is_being_requested = True
        locked_driver.save(update_fields=['is_being_requested'])

    return create_new_ride(locked_driver, ride_request)


def add_to_existing_ride(ride, ride_request):
    """Mavjud hamrohlik safariga yangi yo'lovchi qo'shish."""
    distance = calculate_distance(
        ride_request.pickup_lat, ride_request.pickup_lng,
        ride_request.drop_lat, ride_request.drop_lng,
    )
    fare = calculate_price(
        distance,
        category=ride_request.car_category,
        share_type=ride_request.share_type,
        partners_found=True,
    )

    current_count = ride.passengers.count()
    passenger = RidePassenger.objects.create(
        ride=ride,
        user=ride_request.user,
        ride_request=ride_request,
        pickup_lat=ride_request.pickup_lat,
        pickup_lng=ride_request.pickup_lng,
        pickup_address=ride_request.pickup_address,
        drop_lat=ride_request.drop_lat,
        drop_lng=ride_request.drop_lng,
        drop_address=ride_request.drop_address,
        fare=fare,
        pickup_order=current_count + 1,
        drop_order=current_count + 1,
    )

    ride_request.ride = ride
    ride_request.status = 'matched'
    ride_request.estimated_price = fare
    ride_request.save()

    ride.total_price = sum(p.fare for p in ride.passengers.all())
    ride.save()

    notify_driver_new_ride(ride.driver, ride)

    return {'type': 'shared', 'ride': ride, 'passenger': passenger}


def create_new_ride(driver, ride_request):
    """Yangi safar yaratish va birinchi yo'lovchini qo'shish."""
    distance = calculate_distance(
        ride_request.pickup_lat, ride_request.pickup_lng,
        ride_request.drop_lat, ride_request.drop_lng,
    )
    fare = calculate_price(
        distance,
        category=ride_request.car_category,
        share_type=ride_request.share_type,
        apply_surge=True,
    )

    ride = Ride.objects.create(
        driver=driver,
        status='searching',
        is_shared=ride_request.is_shared,
        total_price=fare,
        total_distance=distance,
    )

    passenger = RidePassenger.objects.create(
        ride=ride,
        user=ride_request.user,
        ride_request=ride_request,
        pickup_lat=ride_request.pickup_lat,
        pickup_lng=ride_request.pickup_lng,
        pickup_address=ride_request.pickup_address,
        drop_lat=ride_request.drop_lat,
        drop_lng=ride_request.drop_lng,
        drop_address=ride_request.drop_address,
        fare=fare,
        pickup_order=1,
        drop_order=1,
    )

    ride_request.ride = ride
    ride_request.status = 'matched'
    ride_request.estimated_price = fare
    ride_request.save()

    logger.info(
        "Yangi safar #%d yaratildi: haydovchi %s, narx %d UZS, masofa %.1f km",
        ride.id, driver.user.phone, fare, distance
    )

    notify_driver_new_ride(driver, ride)

    return {'type': 'new', 'ride': ride, 'passenger': passenger}
