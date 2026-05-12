from math import radians, cos, sin, asin, sqrt
from django.conf import settings
from decimal import Decimal
from .models import PricingRule


def haversine(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula (km)."""
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth radius in km
    return c * r


def calculate_distance(pickup_lat, pickup_lng, drop_lat, drop_lng):
    """Calculate estimated road distance (haversine * 1.3 correction factor)."""
    straight_line = haversine(pickup_lat, pickup_lng, drop_lat, drop_lng)
    # Road distance is typically ~1.3x straight line
    return round(straight_line * 1.3, 2)


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


def calculate_price(distance_km, category='economy', share_type='solo', partners_found=False, shared_distance_ratio=1.0, stops_count=0, is_scheduled=False):
    """
    Calculate ride price with dynamic sharing logic.
    - partners_found: If True, apply discount. If False, charge full price even if requested shared.
    - shared_distance_ratio: If < 0.5, apply only half of the discount.
    """
    distance_km = max(0, float(distance_km or 0))

    # 1. Base Rates based on Category
    rates = {
        'economy': {'base': 6000, 'km': 1500, 'disc_1': 0.15, 'disc_2': 0.30},
        'comfort': {'base': 7000, 'km': 2000, 'disc_1': 0.15, 'disc_2': 0.30},
        'electro': {'base': 7500, 'km': 2300, 'disc_1': 0.20, 'disc_2': 0.40},
        'business': {'base': 10000, 'km': 2800, 'disc_1': 0.20, 'disc_2': 0.40},
    }
    
    r = rates.get(category) or rates['economy']
    
    # 2. Base calculation
    price = r['base'] + (distance_km * r['km'])
    
    # 3. Sharing Logic
    if share_type != 'solo' and partners_found:
        discount = r['disc_1'] if share_type == 'shared_1' else r['disc_2']
        
        # If shared less than 50% of the distance, give only half bonus/discount
        if shared_distance_ratio < 0.5:
            discount = discount / 2
            
        price *= (1 - discount)

    # 4. Add stops fee (2000 per stop)
    price += (max(0, int(stops_count)) * 2000)

    # 5. Add scheduled fee
    if is_scheduled:
        price += 5000

    # Ensure minimum fare (base fare)
    price = max(price, r['base'])

    return int(round(price / 100) * 100)


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
    """Calculate commission. If shared, use a lower commission rate as incentive."""
    pricing = get_active_pricing()
    rate = pricing['commission_rate']
    
    if is_shared:
        # 2% lower commission for shared rides
        rate = max(0.01, rate - 0.02)
        
    commission = total_price * Decimal(str(rate))
    return round(commission, 2)
