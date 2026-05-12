from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Driver, Vehicle, Wallet, WalletTransaction, WalletRequest

# ... existing code ...

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'is_active', 'updated_at']
    search_fields = ['user__phone', 'user__first_name']

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['wallet', 'transaction_type', 'amount', 'status', 'created_at']
    list_filter = ['transaction_type', 'status']
    search_fields = ['wallet__user__phone', 'description']

@admin.register(WalletRequest)
class WalletRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'request_type', 'amount', 'status', 'created_at']
    list_filter = ['request_type', 'status']
    search_fields = ['user__phone', 'user__first_name']
    actions = ['approve_requests', 'reject_requests']

    @admin.action(description='Tanlangan so\'rovlarni tasdiqlash')
    def approve_requests(self, request, queryset):
        for req in queryset:
            if req.status == 'pending':
                req.status = 'approved'
                req.save()

    @admin.action(description='Tanlangan so\'rovlarni rad etish')
    def reject_requests(self, request, queryset):
        queryset.filter(status='pending').update(status='rejected')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['phone', 'first_name', 'last_name', 'role', 'is_verified', 'is_active', 'created_at']
    list_filter = ['role', 'is_verified', 'is_active', 'language']
    search_fields = ['phone', 'first_name', 'last_name']
    ordering = ['-created_at']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Qo\'shimcha', {'fields': ('phone', 'role', 'avatar', 'language', 'is_verified')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Qo\'shimcha', {'fields': ('phone', 'role')}),
    )


class VehicleInline(admin.StackedInline):
    model = Vehicle
    extra = 0


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_car_class', 'status', 'is_online', 'rating', 'total_rides', 'total_earnings']
    list_filter = ['status', 'is_online']
    search_fields = ['user__phone', 'user__first_name', 'license_number']
    inlines = [VehicleInline]
    actions = ['approve_drivers', 'reject_drivers']

    def get_car_class(self, obj):
        try:
            return obj.vehicle.get_car_class_display()
        except:
            return "-"
    get_car_class.short_description = 'Klass (Tarif)'

    @admin.action(description='Tanlangan haydovchilarni tasdiqlash')
    def approve_drivers(self, request, queryset):
        queryset.update(status='approved')

    @admin.action(description='Tanlangan haydovchilarni rad etish')
    def reject_drivers(self, request, queryset):
        queryset.update(status='rejected')


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['driver', 'make', 'model', 'plate_number', 'car_class', 'vehicle_type']
    search_fields = ['plate_number', 'make', 'model']
    list_filter = ['vehicle_type', 'color']
