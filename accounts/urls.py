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
    path('auth/google/', views.google_auth_view, name='google-auth'),
    path('auth/email/', views.email_auth_view, name='email-auth'),


    # Registration
    path('register/', views.register_user_view, name='register-user'),
    path('register/driver/', views.register_driver_view, name='register-driver'),
    path('register/driver/public/', views.register_driver_public_view, name='register-driver-public'),

    # Sayt fikr-mulohaza (reklama sayti)
    path('feedback/', views.site_feedback_view, name='site-feedback'),

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
    path('referral/earnings/', views.referral_earnings_view, name='referral-earnings'),

    # Taksi park (public registration)
    path('taxi-park/register/', views.taxi_park_register_view, name='taxi-park-register'),
    path('taxi-park/list/', views.taxi_park_list_public_view, name='taxi-park-list-public'),
    path('taxi-park/login/', views.taxi_park_login_view, name='taxi-park-login'),

    # Taksi park o'z portali (token orqali)
    path('taxi-park/me/', views.taxi_park_me_view, name='taxi-park-me'),
    path('taxi-park/drivers/', views.taxi_park_drivers_view, name='taxi-park-drivers'),
    path('taxi-park/drivers/pending/', views.taxi_park_pending_drivers_view, name='taxi-park-pending-drivers'),
    path('taxi-park/drivers/<int:driver_id>/', views.taxi_park_driver_detail_view, name='taxi-park-driver-detail'),
    path('taxi-park/drivers/<int:driver_id>/approve/', views.taxi_park_approve_driver_view, name='taxi-park-approve-driver'),
    path('taxi-park/stats/', views.taxi_park_stats_view, name='taxi-park-stats'),
    path('taxi-park/me/update/', views.taxi_park_update_profile_view, name='taxi-park-update-profile'),
    path('taxi-park/change-password/', views.taxi_park_change_password_view, name='taxi-park-change-password'),

    # Admin — Taksi parklar
    path('admin/taxi-parks/', views.AdminTaxiParkListView.as_view(), name='admin-taxi-parks'),
    path('admin/taxi-parks/create/', views.admin_taxi_park_create_view, name='admin-taxi-park-create'),
    path('admin/taxi-parks/<int:pk>/', views.AdminTaxiParkDetailView.as_view(), name='admin-taxi-park-detail'),
    path('admin/taxi-parks/<int:park_id>/action/', views.admin_taxi_park_action, name='admin-taxi-park-action'),
    path('admin/taxi-parks/<int:park_id>/drivers/', views.AdminTaxiParkDriversView.as_view(), name='admin-taxi-park-drivers'),
    path('admin/taxi-parks/<int:park_id>/drivers/add/', views.admin_taxi_park_add_driver, name='admin-taxi-park-add-driver'),
]
