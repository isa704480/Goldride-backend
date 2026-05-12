from django.contrib import admin
from .models import Ride, RideRequest, RidePassenger, RideRating


class RidePassengerInline(admin.TabularInline):
    model = RidePassenger
    extra = 0
    readonly_fields = ['picked_up_at', 'dropped_off_at']


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'driver', 'status', 'is_shared', 'passenger_count',
        'total_price', 'commission_amount', 'driver_earnings',
        'started_at', 'completed_at'
    ]
    list_filter = ['status', 'is_shared', 'created_at']
    search_fields = ['driver__user__phone', 'id']
    inlines = [RidePassengerInline]
    readonly_fields = ['commission_amount', 'driver_earnings']

    def passenger_count(self, obj):
        return obj.passengers.count()
    passenger_count.short_description = "Yo'lovchilar"


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'status', 'estimated_price',
        'estimated_distance', 'is_shared', 'created_at'
    ]
    list_filter = ['status', 'is_shared', 'created_at']
    search_fields = ['user__phone']


@admin.register(RideRating)
class RideRatingAdmin(admin.ModelAdmin):
    list_display = ['ride', 'user', 'rating', 'created_at']
    list_filter = ['rating']
