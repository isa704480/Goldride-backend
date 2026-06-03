import logging
from django.conf import settings

logger = logging.getLogger('rides')


def is_in_tashkent(lat, lng):
    """
    Koordinata faol xizmat hududi (ServiceZone) ichida ekanligini tekshirish.
    DB da zona bo'lmasa — settings.py dagi TASHKENT_BOUNDARY ga qaytadi.
    """
    try:
        from .models import ServiceZone
        result = ServiceZone.is_within_service_area(lat, lng)
        if not result:
            logger.warning("Koordinata xizmat hududidan tashqarida: lat=%.4f, lng=%.4f", lat, lng)
        return result
    except Exception as e:
        logger.error("Geofencing tekshirishda xatolik: %s", e)
        return True


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

        # 2. When driver accepted, also send ride_accepted with full driver info
        if status_text == 'driver_found':
            try:
                ride = Ride.objects.get(id=ride_id)
                from .serializers import RideSerializer
                ride_data = RideSerializer(ride).data
                async_to_sync(channel_layer.group_send)(
                    f'ride_{ride_id}',
                    {
                        'type': 'ride_accepted',
                        'ride': dict(ride_data),
                    }
                )
            except Exception as e:
                logger.error("ride_accepted event xatoligi: %s", e)

        # 3. Notify Admin Group (Dashboard)
        async_to_sync(channel_layer.group_send)(
            'admin_group',
            {
                'type': 'admin_notification',
                'notification_type': 'ride_update',
                'ride_id': ride_id,
                'status': status_text,
            }
        )

    # 4. Telegram Notifications for Passengers
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
            logger.error("Telegram bildirishnoma xatoligi: %s", e)

