from django.contrib import admin
from enrollments.models import Enrollment
from .models import Coupon, Order, PaymentTransaction


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    readonly_fields = ['gateway', 'transaction_reference', 'created_at']


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_percent', 'used_count', 'max_uses', 'valid_until', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['code']
    actions = ['activate_coupons', 'deactivate_coupons']

    @admin.action(description="Activate selected coupons")
    def activate_coupons(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} coupon(s).")

    @admin.action(description="Deactivate selected coupons")
    def deactivate_coupons(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} coupon(s).")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_id', 'user', 'course', 'final_amount', 'status', 'coupon', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['order_id', 'user__username', 'user__email', 'course__title', 'transaction_id']
    readonly_fields = ['order_id', 'created_at', 'updated_at']
    inlines = [PaymentTransactionInline]
    actions = ['mark_as_completed', 'mark_as_refunded']

    @admin.action(description="Mark selected orders as COMPLETED & grant course enrollment")
    def mark_as_completed(self, request, queryset):
        count = 0
        for order in queryset:
            order.status = Order.Status.COMPLETED
            order.save()
            Enrollment.objects.get_or_create(student=order.user, course=order.course)
            count += 1
        self.message_user(request, f"Marked {count} order(s) as COMPLETED and granted course enrollments.")

    @admin.action(description="Mark selected orders as REFUNDED & revoke course enrollment")
    def mark_as_refunded(self, request, queryset):
        count = 0
        for order in queryset:
            order.status = Order.Status.REFUNDED
            order.save()
            Enrollment.objects.filter(student=order.user, course=order.course).delete()
            count += 1
        self.message_user(request, f"Marked {count} order(s) as REFUNDED and revoked enrollments.")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_reference', 'order', 'gateway', 'created_at']
    list_filter = ['gateway', 'created_at']
    search_fields = ['transaction_reference', 'order__order_id', 'order__user__username']
    readonly_fields = ['created_at']
