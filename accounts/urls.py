from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # OTP Auth
    path('send-otp/', views.send_otp_view, name='send-otp'),
    path('verify-otp/', views.verify_otp_view, name='verify-otp'),
    path('login-direct/', views.login_direct_view, name='login-direct'),
    path('admin/login/', views.admin_login_view, name='admin-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram-webhook'),
    path('auth/google/', views.google_auth_view, name='google-auth'),

    # Registration
    path('register/', views.register_user_view, name='register-user'),
    path('register/driver/', views.register_driver_view, name='register-driver'),
    path('register/driver/public/', views.register_driver_public_view, name='register-driver-public'),

    # Profile
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('driver/profile/', views.DriverProfileView.as_view(), name='driver-profile'),
    path('driver/toggle-status/', views.toggle_driver_status, name='toggle-driver-status'),
    path('driver/location/', views.update_driver_location, name='update-driver-location'),
    path('drivers/nearby/', views.NearbyDriversView.as_view(), name='nearby-drivers'),
    
    # Wallet
    path('wallet/', views.get_wallet_view, name='get-wallet'),
    path('wallet/deposit/', views.deposit_wallet_view, name='deposit-wallet'),
    path('wallet/requests/', views.wallet_requests_view, name='wallet-requests'),
    
    # Recommendations
    path('driver/recommendations/', views.get_recommendations, name='get-recommendations'),
    
    # Admin
    path('admin/users/', views.AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<int:pk>/', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:user_id>/action/', views.admin_user_action, name='admin-user-action'),
    path('admin/drivers/', views.AdminDriverListView.as_view(), name='admin-drivers'),
    path('admin/drivers/<int:pk>/', views.AdminDriverDetailView.as_view(), name='admin-driver-detail'),
    path('admin/drivers/<int:driver_id>/action/', views.admin_driver_action, name='admin-driver-action'),

    # Saved Locations
    path('locations/', views.SavedLocationListCreateView.as_view(), name='saved-locations'),
    path('locations/<int:pk>/', views.SavedLocationDeleteView.as_view(), name='saved-location-delete'),

    # Driver goals
    path('driver/goals/', views.driver_goals_view, name='driver-goals'),
    path('driver/goals/select/', views.driver_goal_select_view, name='driver-goal-select'),

    # Referral bonus withdrawal
    path('wallet/withdraw-referral/', views.withdraw_referral_view, name='wallet-withdraw-referral'),
]
