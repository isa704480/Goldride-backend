from rest_framework import serializers
from .models import PricingRule


class PricingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingRule
        fields = '__all__'
