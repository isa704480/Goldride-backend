from django.contrib import admin
from .models import PricingRule


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_fare', 'per_km_rate', 'shared_discount', 'commission_rate', 'is_active']
    list_filter = ['is_active']
