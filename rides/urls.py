from django.urls import path
from . import views

urlpatterns = [
    # Price estimate
    path('estimate/', views.estimate_price, name='estimate-price'),

    # Ride lifecycle
    path('request/', views.request_ride, name='request-ride'),
    path('<int:ride_id>/accept/', views.accept_ride, name='accept-ride'),
    path('<int:ride_id>/mark-arrived/', views.mark_arrived, name='mark-arrived'),
    path('<int:ride_id>/cancel/', views.cancel_ride, name='cancel-ride'),
    path('<int:ride_id>/start/', views.start_ride, name='start-ride'),
    path('<int:ride_id>/complete/', views.complete_ride, name='complete-ride'),

    # Multi-passenger
    path('<int:ride_id>/pickup/<int:passenger_id>/', views.pickup_passenger, name='pickup-passenger'),
    path('<int:ride_id>/dropoff/<int:passenger_id>/', views.dropoff_passenger, name='dropoff-passenger'),

    # Rating
    path('<int:ride_id>/rate/', views.rate_ride, name='rate-ride'),

    # History & earnings
    path('history/', views.RideHistoryView.as_view(), name='ride-history'),
    path('driver/active/', views.DriverActiveRidesView.as_view(), name='driver-active-rides'),
    path('driver/earnings/', views.DriverEarningsView.as_view(), name='driver-earnings'),
    path('active/', views.PassengerActiveRequestView.as_view(), name='passenger-active-request'),
    path('requests/<int:pk>/status/', views.RideRequestStatusView.as_view(), name='request-status'),
    
    # Favorites & Chat
    path('drivers/<int:driver_id>/favorite/', views.toggle_favorite_driver, name='toggle-favorite'),
    path('drivers/favorites/', views.FavoriteDriversListView.as_view(), name='favorite-drivers'),
    path('<int:ride_id>/chat/', views.ChatMessageListCreateView.as_view(), name='ride-chat'),
    
    # Admin & Safety
    path('admin/dashboard-stats/', views.AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('admin/rides/', views.AdminRideListView.as_view(), name='admin-rides'),
    path('admin/rides/<int:pk>/', views.AdminRideDetailView.as_view(), name='admin-ride-detail'),
    path('admin/rides/<int:pk>/complete/', views.admin_complete_ride, name='admin-complete-ride'),
    path('admin/rides/<int:pk>/cancel/', views.admin_cancel_ride, name='admin-cancel-ride'),
    path('admin/requests/<int:request_id>/dispatch-external/', views.admin_dispatch_external, name='admin-dispatch-external'),
    path('admin/requests/<int:request_id>/external-arrived/', views.admin_external_arrived, name='admin-external-arrived'),
    path('admin/requests/<int:request_id>/update-eta/', views.admin_update_external_eta, name='admin-update-eta'),
    path('admin/requests/<int:pk>/cancel/', views.admin_cancel_request, name='admin-cancel-request'),
    path('admin/requests/<int:pk>/', views.AdminRideRequestDetailView.as_view(), name='admin-request-detail'),
    path('admin/analytics/', views.AdminAnalyticsView.as_view(), name='admin-analytics'),
    
    path('sos/', views.trigger_sos, name='trigger-sos'),
    path('<int:ride_id>/chat-history/', views.get_chat_history, name='chat-history'),
    
    # Happy Hours
    path('happy-hours/', views.get_happy_hours, name='happy-hours'),
]
