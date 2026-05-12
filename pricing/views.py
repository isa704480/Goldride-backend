from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from .models import PricingRule
from .serializers import PricingRuleSerializer


class PricingRuleListView(generics.ListCreateAPIView):
    queryset = PricingRule.objects.all()
    serializer_class = PricingRuleSerializer
    permission_classes = [IsAdminUser]


class PricingRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PricingRule.objects.all()
    serializer_class = PricingRuleSerializer
    permission_classes = [IsAdminUser]


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class AdminSettingsView(APIView):
    """Admin-only: Get and update global pricing settings."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        rule = PricingRule.objects.first()
        if not rule:
            # Create a default rule if none exists
            rule = PricingRule.objects.create(name='Default')
        
        return Response(PricingRuleSerializer(rule).data)

    def post(self, request):
        rule = PricingRule.objects.first()
        if not rule:
            rule = PricingRule.objects.create(name='Default')
            
        serializer = PricingRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
