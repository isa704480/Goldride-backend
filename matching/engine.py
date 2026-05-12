"""
Matching Engine — Core algorithm for matching passengers with drivers.

Logic:
1. Find nearby online drivers within SEARCH_RADIUS_KM
2. Check if any driver has an active shared ride with < MAX_PASSENGERS
3. If so, check route deviation — if < MAX_ROUTE_DEVIATION, add to existing ride
4. Otherwise, assign closest available driver
"""

from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from accounts.models import Driver
from rides.models import Ride, RideRequest, RidePassenger
from pricing.engine import haversine, calculate_price, calculate_distance
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notify_driver_new_ride(driver, ride):
    """Send WebSocket notification to driver about new ride request."""
    from rides.serializers import RideSerializer
    
    print(f"[NOTIFY] Sending ride #{ride.id} to driver {driver.user.phone} (group: user_{driver.user.id})")
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{driver.user.id}',
            {
                'type': 'ride_request',
                'ride': RideSerializer(ride).data
            }
        )
        print(f"[NOTIFY] Successfully sent to driver {driver.user.phone}")
    except Exception as e:
        print(f"[NOTIFY ERROR] Failed to send to driver: {e}")
        import traceback
        traceback.print_exc()



def get_nearby_drivers(lat, lng, radius_km=None, requested_category='economy'):
    """
    Find online, approved drivers within radius, filtering by car category,
    minimum balance, and sorting by rating + distance.
    """
    if radius_km is None:
        radius_km = settings.MATCHING['SEARCH_RADIUS_KM']

    # 1. Determine eligible car classes (Hierarchical matching)
    category = requested_category
    if category == 'start':
        category = 'economy'
    
    hierarchy = ['economy', 'comfort', 'electro', 'business']
    try:
        idx = hierarchy.index(category)
        eligible_classes = hierarchy[idx:]
    except ValueError:
        eligible_classes = [category]

    # 2. Filter base drivers (online + approved + location)
    drivers_qs = Driver.objects.filter(
        is_online=True,
        status='approved',
        current_lat__isnull=False,
        current_lng__isnull=False,
        vehicle__car_class__in=eligible_classes
    ).select_related('user', 'vehicle', 'user__wallet')

    # 3. Filter by Minimum Balance
    # Logic: 1st month 40k, after that 20k
    bal_cfg = settings.DRIVER_BALANCE
    first_month_days = bal_cfg.get('FIRST_MONTH_DAYS', 30)
    now = timezone.now()
    
    nearby = []
    for driver in drivers_qs:
        # Calculate distance
        distance = haversine(lat, lng, driver.current_lat, driver.current_lng)
        if distance > radius_km:
            continue
            
        # Check Balance
        try:
            from accounts.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=driver.user)
            balance = wallet.balance
            
            # Determine required minimum
            joined_date = driver.created_at
            if (now - joined_date).days <= first_month_days:
                min_bal = bal_cfg.get('FIRST_MONTH_MINIMUM', 40000)
            else:
                min_bal = bal_cfg.get('AFTER_MONTH_MINIMUM', 20000)
                
            if balance < min_bal:
                print(f"[MATCH] Driver {driver.user.phone} skipped (Low balance: {balance} < {min_bal})")
                continue
        except Exception as e:
            print(f"[MATCH ERROR] Balance check failed for {driver.user.phone}: {e}")
            continue

        nearby.append(driver)

    # 4. Sort by Rating (desc), Balance (desc), and then Distance (asc)
    # Weight: 70% Rating, 30% Balance (normalized to 1M UZS), - Distance
    def ranking_score(d):
        dist = haversine(lat, lng, d.current_lat, d.current_lng)
        rating = float(d.rating or 4.5)
        
        # Balance score: 1.0 if balance >= 1,000,000
        from accounts.models import Wallet
        try:
            balance = float(d.user.wallet.balance)
        except:
            balance = 0
            
        balance_score = min(1.0, balance / 1000000)
        
        # Higher score is better
        return (rating * 0.7) + (balance_score * 1.5) - (dist / radius_km)

    nearby.sort(key=ranking_score, reverse=True)
    
    # Return as list of (driver, distance) for compatibility
    results = []
    for d in nearby:
        dist = haversine(lat, lng, d.current_lat, d.current_lng)
        results.append((d, dist))
        
    print(f"[MATCH] Found {len(results)} eligible drivers (sorted by rating & distance)")
    return results


def calculate_route_deviation(existing_ride, new_request):
    """
    Calculate how much the route deviates if we add a new passenger.

    Simple approach: compare direction vectors.
    Returns deviation as a ratio (0.0 = same direction, 1.0 = opposite).
    """
    # Get existing passenger(s) route vector
    existing_passengers = existing_ride.passengers.all()
    if not existing_passengers:
        return 0.0

    # Average existing destination
    avg_drop_lat = sum(p.drop_lat for p in existing_passengers) / len(existing_passengers)
    avg_drop_lng = sum(p.drop_lng for p in existing_passengers) / len(existing_passengers)

    # Get driver's current position as origin
    driver = existing_ride.driver
    origin_lat = driver.current_lat
    origin_lng = driver.current_lng

    # Existing route distance
    existing_dist = haversine(origin_lat, origin_lng, avg_drop_lat, avg_drop_lng)

    # Distance from driver to new pickup + new dropoff
    new_pickup_detour = haversine(origin_lat, origin_lng, new_request.pickup_lat, new_request.pickup_lng)
    new_drop_dist = haversine(new_request.pickup_lat, new_request.pickup_lng, new_request.drop_lat, new_request.drop_lng)

    # Combined route distance
    combined_dist = new_pickup_detour + new_drop_dist

    if existing_dist == 0:
        return 1.0

    # Deviation = how much longer the route becomes
    deviation = abs(combined_dist - existing_dist) / existing_dist
    return min(deviation, 1.0)


def check_direction_similarity(ride, request):
    """
    Check if the new request goes in a similar direction as existing ride.
    Uses dot product of direction vectors.
    """
    passengers = ride.passengers.all()
    if not passengers:
        return True

    driver = ride.driver

    # Existing direction (driver → avg destination)
    avg_drop_lat = sum(p.drop_lat for p in passengers) / len(passengers)
    avg_drop_lng = sum(p.drop_lng for p in passengers) / len(passengers)

    dir1_lat = avg_drop_lat - driver.current_lat
    dir1_lng = avg_drop_lng - driver.current_lng

    # New request direction (pickup → dropoff)
    dir2_lat = request.drop_lat - request.pickup_lat
    dir2_lng = request.drop_lng - request.pickup_lng

    # Dot product
    dot = dir1_lat * dir2_lat + dir1_lng * dir2_lng
    mag1 = (dir1_lat ** 2 + dir1_lng ** 2) ** 0.5
    mag2 = (dir2_lat ** 2 + dir2_lng ** 2) ** 0.5

    if mag1 == 0 or mag2 == 0:
        return True

    cos_angle = dot / (mag1 * mag2)

    # Similar direction if cosine > 0.5 (within ~60 degrees)
    return cos_angle > 0.5


def find_match(ride_request):
    """
    Main matching function.

    1. Find nearby drivers
    2. Try to add to existing shared ride
    3. If not possible, assign new driver
    """
    max_passengers = settings.PRICING.get('MAX_PASSENGERS_PER_RIDE', 2)
    max_deviation = settings.MATCHING.get('MAX_ROUTE_DEVIATION', 0.20)
    time_window = settings.MATCHING.get('MATCH_TIME_WINDOW_MINUTES', 5)

    nearby_drivers = get_nearby_drivers(
        ride_request.pickup_lat,
        ride_request.pickup_lng,
        requested_category=ride_request.car_category
    )

    if not nearby_drivers:
        return None

    # Step 1: Try to join an existing shared ride
    if ride_request.is_shared:
        for driver, distance in nearby_drivers:
            active_rides = Ride.objects.filter(
                driver=driver,
                is_shared=True,
                status__in=['searching', 'driver_found', 'on_the_way'],
                created_at__gte=timezone.now() - timedelta(minutes=time_window * 3)
            ).prefetch_related('passengers')

            for ride in active_rides:
                if ride.passengers.count() >= max_passengers:
                    continue

                # Check route compatibility
                deviation = calculate_route_deviation(ride, ride_request)
                if deviation > max_deviation:
                    continue

                # Check direction similarity
                if not check_direction_similarity(ride, ride_request):
                    continue

                # Match found! Add to existing ride
                return add_to_existing_ride(ride, ride_request)

    # Step 2: Assign new driver (closest available without active ride)
    for driver, distance in nearby_drivers:
        has_active = Ride.objects.filter(
            driver=driver,
            status__in=['searching', 'driver_found', 'on_the_way', 'started']
        ).exists()

        # For shared rides, allow drivers with one active ride
        if has_active and not ride_request.is_shared:
            continue

        if has_active:
            # Check if their active ride can accept another passenger
            active_ride = Ride.objects.filter(
                driver=driver,
                status__in=['searching', 'driver_found', 'on_the_way'],
                is_shared=True,
            ).prefetch_related('passengers').first()

            if active_ride and active_ride.passengers.count() < max_passengers:
                deviation = calculate_route_deviation(active_ride, ride_request)
                if deviation <= max_deviation:
                    return add_to_existing_ride(active_ride, ride_request)
            continue

        # Create new ride
        return create_new_ride(driver, ride_request)

    return None


def add_to_existing_ride(ride, ride_request):
    """Add a passenger to an existing shared ride."""
    # Calculate individual fare
    distance = calculate_distance(
        ride_request.pickup_lat, ride_request.pickup_lng,
        ride_request.drop_lat, ride_request.drop_lng
    )
    fare = calculate_price(
        distance, 
        category=ride_request.car_category, 
        share_type=ride_request.share_type,
        partners_found=True
    )

    # Determine pickup/drop order
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

    # Update ride request
    ride_request.ride = ride
    ride_request.status = 'matched'
    ride_request.estimated_price = fare
    ride_request.save()

    # Update total price
    ride.total_price = sum(p.fare for p in ride.passengers.all())
    ride.save()

    # Notify driver
    notify_driver_new_ride(ride.driver, ride)

    return {
        'type': 'shared',
        'ride': ride,
        'passenger': passenger,
    }


def create_new_ride(driver, ride_request):
    """Create a new ride with the first passenger."""
    distance = calculate_distance(
        ride_request.pickup_lat, ride_request.pickup_lng,
        ride_request.drop_lat, ride_request.drop_lng
    )
    fare = calculate_price(
        distance, 
        category=ride_request.car_category, 
        share_type=ride_request.share_type
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

    # Notify driver
    notify_driver_new_ride(driver, ride)

    return {
        'type': 'new',
        'ride': ride,
        'passenger': passenger,
    }
