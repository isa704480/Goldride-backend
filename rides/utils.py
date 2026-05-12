from django.conf import settings

def is_in_tashkent(lat, lng):
    """
    Checks if the given coordinates are within the Tashkent boundary defined in settings.
    """
    boundary = getattr(settings, 'TASHKENT_BOUNDARY', None)
    if not boundary:
        return True # Default to True if no boundary defined
    
    try:
        lat = float(lat)
        lng = float(lng)
        return (
            boundary['LAT_MIN'] <= lat <= boundary['LAT_MAX'] and
            boundary['LNG_MIN'] <= lng <= boundary['LNG_MAX']
        )
    except (ValueError, TypeError):
        return False


def notify_ride_status_update(ride_id, status_text):
    """Notify all participants of a ride about a status change via WebSocket and Telegram."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .models import Ride
    from accounts.utils import send_telegram_notification
    
    channel_layer = get_channel_layer()
    if channel_layer:
        # 1. Notify Ride Group (Driver & Passengers)
        async_to_sync(channel_layer.group_send)(
            f'ride_{ride_id}',
            {
                'type': 'ride_status_update',
                'ride_id': ride_id,
                'status': status_text,
            }
        )

        # 2. Notify Admin Group (Dashboard)
        async_to_sync(channel_layer.group_send)(
            'admin_group',
            {
                'type': 'admin_notification',
                'notification_type': 'ride_update',
                'ride_id': ride_id,
                'status': status_text,
            }
        )

    # 3. Telegram Notifications for Passengers
    if status_text == 'driver_found':
        try:
            ride = Ride.objects.get(id=ride_id)
            driver = ride.driver
            if driver:
                v = driver.vehicle
                car_info = f"{v.color} {v.make} {v.model} ({v.plate_number})" if v else "Mashina ma'lumoti yo'q"
                
                msg = (
                    f"🚕 Safaringiz qabul qilindi!\n\n"
                    f"👨‍✈️ Haydovchi: {driver.user.get_full_name()}\n"
                    f"📞 Tel: {driver.user.phone}\n"
                    f"🚘 Mashina: {car_info}\n\n"
                    f"Oq yo'l! ✨"
                )
                
                for request in ride.requests.all():
                    user = request.user
                    if user.telegram_chat_id:
                        # Use the specific chat_id of the user
                        from accounts.utils import send_telegram_notification
                        send_telegram_notification(msg, chat_id=user.telegram_chat_id)
        except Exception as e:
            print(f"Telegram notification error: {e}")

