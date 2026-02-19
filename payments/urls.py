from django.urls import path
from .views import razorpay_webhook

urlpatterns = [
    path('razorpay/webhook/', razorpay_webhook, name='razorpay-webhook'),
]
