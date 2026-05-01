from django.urls import path
from .views import integration_health, razorpay_webhook

urlpatterns = [
    path('payments/health/', integration_health, name='integration-health'),
    path('razorpay/webhook/', razorpay_webhook, name='razorpay-webhook'),
]
