from django.urls import path
from .views import integration_health, razorpay_webhook, webhook_debug_guide

urlpatterns = [
    path('payments/health/', integration_health, name='integration-health'),
    path('payments/webhook-debug/', webhook_debug_guide, name='webhook-debug-guide'),
    path('razorpay/webhook/', razorpay_webhook, name='razorpay-webhook'),
]
