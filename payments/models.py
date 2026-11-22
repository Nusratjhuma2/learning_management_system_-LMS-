import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    """Discount coupon code for course purchases."""

    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text='Percentage discount (1 - 100)',
    )
    course = models.ForeignKey(
        'courses.Course',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='coupons',
        help_text="Course this coupon applies to. Leave blank for all courses (Admin only).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='created_coupons',
    )
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(default=100)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self, course=None):
        """Validates whether the coupon can be applied."""
        if not self.is_active:
            return False, "This coupon code is deactivated."
        if self.valid_until and timezone.now() > self.valid_until:
            return False, "This coupon has expired."
        if self.used_count >= self.max_uses:
            return False, "This coupon has reached its maximum redemption limit."
        if self.course and course and self.course != course:
            return False, f"This coupon is only valid for '{self.course.title}'."
        return True, "Coupon is valid."

    @property
    def is_site_wide(self):
        return self.course is None

    @property
    def is_expired(self):
        return bool(self.valid_until and timezone.now() > self.valid_until)

    @property
    def status_label(self):
        if not self.is_active:
            return "Deactivated"
        if self.is_expired:
            return "Expired"
        if self.used_count >= self.max_uses:
            return "Limit Reached"
        return "Active"

    def __str__(self):
        scope = self.course.title if self.course else "All Courses"
        return f"{self.code} (-{self.discount_percent}% on {scope})"


class Order(models.Model):
    """Financial order record for a course purchase."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    order_id = models.CharField(max_length=64, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    coupon = models.ForeignKey(
        Coupon,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='orders',
    )
    original_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    transaction_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.user.username} (${self.final_amount})"


class PaymentTransaction(models.Model):
    """Detailed gateway transaction log for an order."""

    GATEWAY_CHOICES = [
        ('mock', 'Mock / Direct Sandbox'),
        ('stripe', 'Stripe'),
        ('bkash', 'bKash'),
        ('sslcommerz', 'SSLCommerz'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='mock')
    transaction_reference = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.gateway.upper()} - {self.transaction_reference} ({self.order.order_id})"
