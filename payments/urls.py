from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<slug:course_slug>/', views.checkout, name='checkout'),
    path('process/<str:order_id>/', views.process_mock_payment, name='process_payment'),
    path('invoice/<str:order_id>/', views.order_invoice, name='order_invoice'),
    path('history/', views.student_order_history, name='order_history'),
]

