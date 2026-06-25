import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


class RideConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time ride updates.

    Events handled:
    - Client → Server:
        - request_ride: Passenger requests a ride
        - accept_ride: Driver accepts a ride
        - driver_location_update: Driver sends location
        - cancel_ride: Cancel a ride

    - Server → Client:
        - ride_request: New ride request for driver
        - ride_accepted: Ride was accepted
        - driver_location: Driver's current location
        - ride_status_update: Ride status changed
        - passenger_added: New passenger added to shared ride
    """

    async def connect(self):
        try:
            self.user = self.scope.get('user', AnonymousUser())

            if isinstance(self.user, AnonymousUser) or not self.user.is_authenticated:
                await self.close()
                return

            # Join user's personal channel
            self.user_group = f'user_{self.user.id}'
            await self.channel_layer.group_add(self.user_group, self.channel_name)

            # If driver, join drivers channel
            if getattr(self.user, 'role', '') == 'driver':
                self.driver_group = 'drivers_online'
                await self.channel_layer.group_add(self.driver_group, self.channel_name)

            await self.accept()
            await self.send_json({
                'type': 'connected',
                'message': 'WebSocket ulandi',
                'user_id': self.user.id,
            })
        except Exception as e:
            import traceback
            print(f"[WS Connect Error] {e}")
            traceback.print_exc()
            raise e

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'driver_group'):
            await self.channel_layer.group_discard(self.driver_group, self.channel_name)
        if hasattr(self, 'ride_group'):
            await self.channel_layer.group_discard(self.ride_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle incoming WebSocket messages."""
        event_type = content.get('type')

        handlers = {
            'join_ride': self.handle_join_ride,
            'driver_location_update': self.handle_driver_location,
            'cancel_ride': self.handle_cancel_ride,
            'accept_ride': self.handle_accept_ride,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(content)
        else:
            await self.send_json({
                'type': 'error',
                'message': f'Noma\'lum event turi: {event_type}'
            })

    async def handle_join_ride(self, data):
        """Join a ride's real-time channel."""
        ride_id = data.get('ride_id')
        if ride_id:
            self.ride_group = f'ride_{ride_id}'
            await self.channel_layer.group_add(self.ride_group, self.channel_name)
            await self.send_json({
                'type': 'joined_ride',
                'ride_id': ride_id,
            })

    async def handle_driver_location(self, data):
        """Driver sends location update — broadcast to ride passengers."""
        lat = data.get('lat')
        lng = data.get('lng')

        if lat is None or lng is None:
            return

        # Update driver location in DB
        await self.update_driver_location(lat, lng)

        # Broadcast to ride group
        if hasattr(self, 'ride_group'):
            await self.channel_layer.group_send(
                self.ride_group,
                {
                    'type': 'driver_location',
                    'lat': lat,
                    'lng': lng,
                    'driver_id': self.user.id,
                }
            )

        # Broadcast to Admin Group
        await self.channel_layer.group_send(
            'admin_group',
            {
                'type': 'admin_notification',
                'notification_type': 'driver_location',
                'driver_id': self.user.id,
                'lat': lat,
                'lng': lng,
            }
        )

    async def handle_accept_ride(self, data):
        """Driver accepts a ride."""
        ride_id = data.get('ride_id')
        if not ride_id:
            return

        ride = await self.accept_ride_db(ride_id)
        if ride:
            from rides.serializers import RideSerializer
            
            # Join ride group
            self.ride_group = f'ride_{ride_id}'
            await self.channel_layer.group_add(self.ride_group, self.channel_name)

            # Serialize full ride data for passengers
            serializer_data = await self.serialize_ride(ride)

            # Notify passengers in the ride group
            await self.channel_layer.group_send(
                self.ride_group,
                {
                    'type': 'ride_accepted',
                    'ride': serializer_data,
                }
            )
            
            # Notify Admin
            await self.channel_layer.group_send(
                'admin_group',
                {
                    'type': 'admin_notification',
                    'notification_type': 'ride_update',
                    'ride_id': ride_id,
                    'status': 'driver_found',
                    'driver_name': self.user.get_full_name(),
                }
            )

    async def handle_cancel_ride(self, data):
        """Handle ride cancellation."""
        ride_id = data.get('ride_id')
        if not ride_id:
            return

        if hasattr(self, 'ride_group'):
            await self.channel_layer.group_send(
                self.ride_group,
                {
                    'type': 'ride_status_update',
                    'ride_id': ride_id,
                    'status': 'cancelled',
                    'cancelled_by': self.user.id,
                }
            )

    # ---- Channel Layer Event Handlers (sent from group_send) ----

    async def ride_request(self, event):
        """Forward ride request to driver."""
        await self.send_json(event)

    async def ride_accepted(self, event):
        """Forward ride accepted to passengers."""
        await self.send_json(event)

    async def driver_location(self, event):
        """Forward driver location to passengers."""
        await self.send_json(event)

    async def ride_status_update(self, event):
        """Forward ride status update."""
        await self.send_json(event)

    async def passenger_added(self, event):
        """Notify when a new passenger is added to shared ride."""
        await self.send_json(event)

    # ---- Database Operations ----

    @database_sync_to_async
    def update_driver_location(self, lat, lng):
        from accounts.models import Driver
        try:
            driver = self.user.driver_profile
            driver.current_lat = lat
            driver.current_lng = lng
            driver.save(update_fields=['current_lat', 'current_lng', 'updated_at'])
        except Exception:
            pass

    @database_sync_to_async
    def serialize_ride(self, ride):
        from rides.serializers import RideSerializer
        return RideSerializer(ride).data

    @database_sync_to_async
    def accept_ride_db(self, ride_id):
        from rides.models import Ride
        from django.db import transaction
        try:
            driver = self.user.driver_profile
            with transaction.atomic():
                ride = Ride.objects.select_for_update().get(id=ride_id)
                # Allaqachon boshqa haydovchi qabul qilgan bo'lsa — rad etamiz
                if ride.driver_id and ride.driver_id != driver.id:
                    return None
                ride.driver = driver
                ride.status = 'driver_found'
                ride.save(update_fields=['driver', 'status'])
                driver.is_being_requested = False
                driver.save(update_fields=['is_being_requested'])
                ride.requests.filter(status='matched').update(status='accepted')
            return ride
        except Exception:
            return None


class AdminConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for admin dashboard.
    Receives global notifications about new rides, fraud alerts, etc.
    """

    async def connect(self):
        self.user = self.scope.get('user', AnonymousUser())

        if isinstance(self.user, AnonymousUser) or not self.user.is_staff:
            await self.close()
            return

        # Join admin group
        self.admin_group = 'admin_group'
        await self.channel_layer.group_add(self.admin_group, self.channel_name)

        await self.accept()
        await self.send_json({
            'type': 'connected',
            'message': 'Admin WebSocket ulandi'
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'admin_group'):
            await self.channel_layer.group_discard(self.admin_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Admin can send commands if needed
        pass

    async def admin_notification(self, event):
        """Forward admin notification to dashboard."""
        await self.send_json(event)

