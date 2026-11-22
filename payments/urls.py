from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<slug:course_slug>/', views.checkout, name='checkout'),
    path('process/<str:order_id>/', views.process_mock_payment, name='process_payment'),
    path('invoice/<str:order_id>/', views.order_invoice, name='order_invoice'),
    path('history/', views.student_order_history, name='order_history'),
    path('coupons/', views.coupon_list, name='coupon_list'),
    path('coupons/create/', views.coupon_create, name='coupon_create'),
    path('coupons/<int:coupon_id>/edit/', views.coupon_edit, name='coupon_edit'),
    path('coupons/<int:coupon_id>/toggle/', views.coupon_toggle_status, name='coupon_toggle_status'),
    path('coupons/<int:coupon_id>/delete/', views.coupon_delete, name='coupon_delete'),
]

