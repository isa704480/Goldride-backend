from rest_framework import serializers
from .models import Ride, RideRequest, RidePassenger, RideRating, RideStop, ChatMessage
from accounts.serializers import UserProfileSerializer, DriverProfileSerializer


class RidePassengerSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = RidePassenger
        fields = [
            'id', 'user', 'pickup_lat', 'pickup_lng', 'pickup_address',
            'drop_lat', 'drop_lng', 'drop_address', 'fare',
            'pickup_order', 'drop_order', 'picked_up', 'dropped_off',
            'picked_up_at', 'dropped_off_at'
        ]


class RideSerializer(serializers.ModelSerializer):
    driver = DriverProfileSerializer(read_only=True)
    passengers = RidePassengerSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    passenger_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ride
        fields = [
            'id', 'driver', 'status', 'status_display', 'is_shared',
            'total_price', 'total_distance', 'commission_rate',
            'commission_amount', 'driver_earnings', 'passenger_count',
            'passengers', 'route_polyline',
            'started_at', 'completed_at', 'created_at'
        ]


class RideStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideStop
        fields = ['address', 'latitude', 'longitude', 'order']


class RideRequestCreateSerializer(serializers.ModelSerializer):
    stops = RideStopSerializer(many=True, required=False)

    class Meta:
        model = RideRequest
        fields = [
            'pickup_lat', 'pickup_lng', 'pickup_address',
            'drop_lat', 'drop_lng', 'drop_address',
            'is_shared', 'share_type', 'use_bonus', 'bonus_percent', 'car_category', 'is_scheduled', 'scheduled_time', 'stops'
        ]

    def create(self, validated_data):
        stops_data = validated_data.pop('stops', [])
        ride_request = RideRequest.objects.create(**validated_data)
        for stop_data in stops_data:
            RideStop.objects.create(ride_request=ride_request, **stop_data)
        return ride_request


class RideRequestSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    ride = RideSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    stops = RideStopSerializer(many=True, read_only=True)

    class Meta:
        model = RideRequest
        fields = [
            'id', 'user', 'ride', 'pickup_lat', 'pickup_lng', 'pickup_address',
            'drop_lat', 'drop_lng', 'drop_address',
            'estimated_price', 'estimated_distance', 'estimated_duration',
            'is_shared', 'share_type', 'is_scheduled', 'scheduled_time', 'status',
            'status_display', 'stops', 'external_provider', 'external_order_id', 'external_eta', 'created_at'
        ]


class RideRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideRating
        fields = ['id', 'ride', 'target_user', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']


class PriceEstimateSerializer(serializers.Serializer):
    pickup_lat = serializers.FloatField()
    pickup_lng = serializers.FloatField()
    drop_lat = serializers.FloatField()
    drop_lng = serializers.FloatField()
    is_shared = serializers.BooleanField(default=True)
    share_type = serializers.CharField(default='solo')
    is_scheduled = serializers.BooleanField(default=False)
    stops_count = serializers.IntegerField(default=0)


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['id', 'ride', 'sender', 'sender_name', 'content', 'is_read', 'created_at']
        read_only_fields = ['id', 'sender', 'created_at']
