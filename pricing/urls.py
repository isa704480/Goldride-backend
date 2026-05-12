from django.urls import path
from . import views

urlpatterns = [
    path('rules/', views.PricingRuleListView.as_view(), name='pricing-rules'),
    path('rules/<int:pk>/', views.PricingRuleDetailView.as_view(), name='pricing-rule-detail'),
    path('admin/settings/', views.AdminSettingsView.as_view(), name='admin-settings'),
]
