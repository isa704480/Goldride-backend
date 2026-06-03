import logging
from math import radians, cos, sin, asin, sqrt
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP
from .models import PricingRule

logger = logging.getLogger('pricing')

# Toshkent shahri uchun yo'l masofasi koeffitsienti.
# Haversine (qush uchishi) masofasidan yo'ldagi masofa taxminan 35% ko'p.
TASHKENT_ROAD_FACTOR = 1.35

# Toshkentda o'rtacha harakatlanish tezligi (km/h) — ETA hisoblash uchun
AVG_SPEED_KMH = 28.0


def haversine(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula (km)."""
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371
    return c * r


def calculate_distance(pickup_lat, pickup_lng, drop_lat, drop_lng):
    """
    Haqiqiy yo'l masofasini hisoblash.
    Toshkent uchun Haversine * 1.35 koeffitsienti ishlatiladi,
    chunki shahar ko'chalari qushning uchish yo'lidan ~35% uzunroq.
    """
    straight_line = haversine(pickup_lat, pickup_lng, drop_lat, drop_lng)
    return round(straight_line * TASHKENT_ROAD_FACTOR, 2)


def estimate_duration_minutes(distance_km):
    """Masofa bo'yicha taxminiy vaqtni (daqiqa) hisoblash."""
    return round((distance_km / AVG_SPEED_KMH) * 60, 1)


def get_active_pricing():
    """Get active pricing rule or return defaults."""
    try:
        rule = PricingRule.objects.filter(is_active=True).first()
        if rule:
            return {
                'base_fare': rule.base_fare,
                'per_km_rate': rule.per_km_rate,
                'shared_discount': rule.shared_discount,
                'commission_rate': rule.commission_rate,
                'min_fare': rule.min_fare,
                'multi_stop_fee': rule.multi_stop_fee,
                'scheduled_fee': rule.scheduled_fee,
                'cancellation_fee': rule.cancellation_fee,
                'waiting_rate_per_min': rule.waiting_rate_per_min,
            }
    except Exception:
        pass

    # Fallback to settings
    pricing = getattr(settings, 'PRICING', {})
    return {
        'base_fare': pricing.get('BASE_FARE', 6000),
        'per_km_rate': pricing.get('PER_KM_RATE', 1500),
        'shared_discount': pricing.get('SHARED_DISCOUNT', 0.3),
        'commission_rate': pricing.get('COMMISSION_RATE', 0.05),
        'min_fare': pricing.get('MIN_FARE', 5000),
        'multi_stop_fee': pricing.get('MULTI_STOP_FEE', 2000),
        'scheduled_fee': pricing.get('SCHEDULED_FEE', 5000),
        'cancellation_fee': pricing.get('CANCELLATION_FEE', 2000),
        'waiting_rate_per_min': pricing.get('WAITING_RATE_PER_MIN', 500),
    }


def get_surge_multiplier():
    """
    Hozirgi talab/taklif nisbatiga qarab surge koeffitsientini hisoblash.

    demand_ratio = faol so'rovlar / onlayn haydovchilar

    > 2.0  → narx 1.5 barobar (juda ko'p yo'lovchi, kam mashina)
    > 1.5  → narx 1.25 barobar (talab biroz oshib turgan)
    ≤ 1.5  → oddiy narx (1.0)

    Cache ishlatiladi (30 soniya) — har so'rovda DB ga urilmaslik uchun.
    """
    from django.core.cache import cache
    cached = cache.get('surge_multiplier')
    if cached is not None:
        return cached

    try:
        from rides.models import RideRequest
        from accounts.models import Driver

        active_requests = RideRequest.objects.filter(status='searching').count()
        available_drivers = Driver.objects.filter(
            is_online=True, status='approved', is_being_requested=False
        ).count()

        if available_drivers == 0:
            multiplier = 1.5
        else:
            ratio = active_requests / available_drivers
            if ratio > 2.0:
                multiplier = 1.5
            elif ratio > 1.5:
                multiplier = 1.25
            else:
                multiplier = 1.0

        logger.info(
            "Surge: so'rovlar=%d, haydovchilar=%d → %.2fx",
            active_requests, available_drivers, multiplier
        )
    except Exception as e:
        logger.warning("Surge hisoblashda xatolik: %s", e)
        multiplier = 1.0

    cache.set('surge_multiplier', multiplier, 30)
    return multiplier


def calculate_price(
    distance_km,
    category='economy',
    share_type='solo',
    partners_found=False,
    shared_distance_ratio=1.0,
    stops_count=0,
    is_scheduled=False,
    apply_surge=False,
):
    """
    Safar narxini hisoblash.

    distance_km        — haqiqiy yo'l masofasi (calculate_distance() natijasi)
    partners_found     — True bo'lsa chegirma qo'llanadi
    shared_distance_ratio — 0.5 dan kam bo'lsa, chegirma yarmi qo'llanadi
    stops_count        — qo'shimcha to'xtashlar soni
    is_scheduled       — oldindan buyurtma bo'lsa qo'shimcha to'lov
    apply_surge        — True bo'lsa talab/taklif surge qo'llanadi
    """
    distance_km = max(0.0, float(distance_km or 0))

    # Har bir avtomobil klassi uchun tariflar (UZS)
    rates = {
        'economy':  {'base': 6000, 'km': 1500, 'per_min': 200, 'disc_1': 0.15, 'disc_2': 0.30},
        'comfort':  {'base': 7000, 'km': 2000, 'per_min': 250, 'disc_1': 0.15, 'disc_2': 0.30},
        'electro':  {'base': 7500, 'km': 2300, 'per_min': 280, 'disc_1': 0.20, 'disc_2': 0.40},
        'business': {'base': 10000,'km': 2800, 'per_min': 350, 'disc_1': 0.20, 'disc_2': 0.40},
    }
    r = rates.get(category) or rates['economy']

    # 1. Asosiy narx = bazaviy + masofa + vaqt
    duration_min = estimate_duration_minutes(distance_km)
    price = r['base'] + (distance_km * r['km']) + (duration_min * r['per_min'])

    # 2. Hamrohlik chegirmasi
    if share_type != 'solo' and partners_found:
        discount = r['disc_1'] if share_type == 'shared_1' else r['disc_2']
        if shared_distance_ratio < 0.5:
            discount /= 2
        price *= (1 - discount)

    # 3. To'xtash haqi: har bir qo'shimcha to'xtash uchun 2000 UZS
    price += max(0, int(stops_count)) * 2000

    # 4. Oldindan buyurtma qo'shimchasi
    if is_scheduled:
        price += 5000

    # 5. Surge: talab ko'p, haydovchi kam bo'lsa narx oshadi
    surge = get_surge_multiplier() if apply_surge else 1.0
    if surge > 1.0:
        price *= surge
        logger.info("Surge %.2fx qo'llandi: %d UZS → %d UZS", surge, int(price / surge), int(price))

    # Minimal narx: avtomobil klassi bazaviy tariflari
    price = max(price, r['base'])

    # 500 UZS ga yaxlitlash (foydalanuvchiga qulay)
    price = round(price / 500) * 500

    logger.debug("Narx hisoblandi: %.1f km, %s klass, surge=%.2f → %d UZS", distance_km, category, surge, price)
    return int(price)


def recalculate_ride_fares(ride):
    """
    Final recalculation of fares for all passengers in a ride at completion.
    Based on actual shared distance and presence of partners.
    """
    passengers = list(ride.passengers.all())
    count = len(passengers)
    total_fare = 0
    
    for p in passengers:
        req = p.ride_request
        if not req: continue
        
        partners_found = count > 1
        shared_ratio = 0.0
        
        if partners_found:
            # Basic overlap estimation:
            # We look for other passengers who were in the car while this passenger was also there.
            # For simplicity, we compare the distance between the "shared" segments.
            # Let's find the maximum shared distance with ANY partner.
            max_shared_dist = 0
            p_total_dist = float(req.estimated_distance or 0)
            
            for other in passengers:
                if other.id == p.id: continue
                
                # Shared part starts at max(p.pickup, other.pickup) 
                # and ends at min(p.dropoff, other.dropoff)
                # We use coordinates to estimate this.
                # This is a heuristic: we assume the shared part is between 
                # the 'later' pickup and the 'earlier' dropoff.
                
                # We don't have the order easily here, but we can check distance 
                # between the points that are likely shared.
                
                # For now, if there is another passenger, we check if they are "compatible"
                # A better way is to use the pickup_order/drop_order
                shared_dist = 0
                if p.pickup_order < other.drop_order and other.pickup_order < p.drop_order:
                    # They overlapped. 
                    # Approximate shared distance as distance between 
                    # the points they were both present.
                    # This is very rough but better than nothing.
                    shared_dist = p_total_dist * 0.8 # Assume 80% overlap if they were together
                
                max_shared_dist = max(max_shared_dist, shared_dist)
            
            if p_total_dist > 0:
                shared_ratio = max_shared_dist / p_total_dist
            else:
                shared_ratio = 1.0

        actual_fare = calculate_price(
            distance_km=req.estimated_distance,
            category=req.car_category,
            share_type=req.share_type,
            partners_found=partners_found,
            shared_distance_ratio=shared_ratio,
            stops_count=req.stops.count(),
            is_scheduled=req.is_scheduled
        )
        p.fare = actual_fare
        p.save(update_fields=['fare'])
        total_fare += actual_fare
        
    ride.total_price = total_fare
    ride.save(update_fields=['total_price'])
    return total_fare


def calculate_commission(total_price, is_shared=False):
    """
    Komissiya hisoblash. Floating point xatoliklaridan himoya uchun Decimal ishlatiladi.
    Hamrohlik safarlarida komissiya 2% past — haydovchi uchun rag'bat.
    """
    pricing = get_active_pricing()
    rate = Decimal(str(pricing['commission_rate']))

    if is_shared:
        rate = max(Decimal('0.01'), rate - Decimal('0.02'))

    price_dec = Decimal(str(total_price))
    commission = (price_dec * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(commission)
