import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.models import Course
from enrollments.models import Enrollment
from .models import Coupon, Order, PaymentTransaction


@login_required
def checkout(request, course_slug):
    """
    Checkout portal for enrolling in paid courses.
    Supports coupon discounts, automatic zero-amount enrollment, and gateway selection.
    """
    course = get_object_or_404(Course, slug=course_slug, status=Course.Status.PUBLISHED)

    # If student is already enrolled
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.info(request, f"You are already enrolled in '{course.title}'.")
        return redirect('courses:course_detail', slug=course.slug)

    # Base price calculation
    course_price = course.discount_price if (course.discount_price and course.discount_price > 0) else course.price
    course_price = Decimal(str(course_price or '0.00'))

    # Free course auto-enrollment
    if course.is_free or course_price <= Decimal('0.00'):
        Enrollment.objects.get_or_create(student=request.user, course=course)
        messages.success(request, f"Free enrollment confirmed for '{course.title}'!")
        return redirect('courses:course_detail', slug=course.slug)

    applied_coupon = None
    discount_amount = Decimal('0.00')
    coupon_error = None
    coupon_code = request.GET.get('coupon', '').strip() or request.POST.get('coupon_code', '').strip()

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
            is_valid, reason = coupon.is_valid()
            if is_valid:
                applied_coupon = coupon
                discount_amount = round(course_price * Decimal(str(coupon.discount_percent / 100)), 2)
            else:
                coupon_error = reason
        except Coupon.DoesNotExist:
            coupon_error = "Invalid coupon code."

    final_amount = max(Decimal('0.00'), course_price - discount_amount)

    # Retrieve or create a pending order
    order, created = Order.objects.get_or_create(
        user=request.user,
        course=course,
        status=Order.Status.PENDING,
        defaults={
            'original_amount': course_price,
            'discount_amount': discount_amount,
            'final_amount': final_amount,
            'coupon': applied_coupon,
        }
    )

    if not created:
        order.original_amount = course_price
        order.discount_amount = discount_amount
        order.final_amount = final_amount
        order.coupon = applied_coupon
        order.save()

    # 100% discount auto-completion
    if final_amount == Decimal('0.00') and applied_coupon:
        order.status = Order.Status.COMPLETED
        order.transaction_id = f"FREE-COUPON-{uuid.uuid4().hex[:8].upper()}"
        order.save()

        applied_coupon.used_count += 1
        applied_coupon.save()

        Enrollment.objects.get_or_create(student=request.user, course=course)
        messages.success(request, f"100% Coupon applied! Enrolled in '{course.title}'.")
        return redirect('payments:order_invoice', order_id=order.order_id)

    return render(request, 'payments/checkout.html', {
        'course': course,
        'order': order,
        'course_price': course_price,
        'regular_price': course.price,
        'has_course_discount': course.has_discount,
        'course_discount_savings': course.savings_amount,
        'course_discount_percentage': course.discount_percentage,
        'discount_amount': discount_amount,
        'final_amount': final_amount,
        'applied_coupon': applied_coupon,
        'coupon_error': coupon_error,
        'coupon_code': coupon_code,
    })


@login_required
@require_POST
def process_mock_payment(request, order_id):
    """
    Executes mock / sandbox payment checkout.
    Marks order completed, creates PaymentTransaction log, and auto-enrolls student.
    """
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.status == Order.Status.COMPLETED:
        messages.info(request, "This order has already been completed.")
        return redirect('payments:order_invoice', order_id=order.order_id)

    gateway = request.POST.get('gateway', 'mock')
    tx_ref = f"TXN-{gateway.upper()}-{uuid.uuid4().hex[:10].upper()}"

    order.status = Order.Status.COMPLETED
    order.transaction_id = tx_ref
    order.save()

    PaymentTransaction.objects.create(
        order=order,
        gateway=gateway,
        transaction_reference=tx_ref,
        payload={
            'simulated_at': timezone.now().isoformat(),
            'amount': str(order.final_amount),
            'currency': 'USD',
            'status': 'SUCCESS',
            'buyer_email': request.user.email,
        }
    )

    if order.coupon:
        order.coupon.used_count += 1
        order.coupon.save()

    # Create enrollment
    Enrollment.objects.get_or_create(student=order.user, course=order.course)

    messages.success(request, f"Payment successful! You have unlocked '{order.course.title}'.")
    return redirect('payments:order_invoice', order_id=order.order_id)


@login_required
def order_invoice(request, order_id):
    """
    Displays a formal, printable invoice for course purchase records.
    """
    order = get_object_or_404(
        Order.objects.select_related('user', 'course', 'course__instructor', 'coupon'),
        order_id=order_id,
    )

    is_buyer = order.user == request.user
    is_staff = request.user.is_staff or getattr(request.user, 'is_admin', False)

    if not is_buyer and not is_staff:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_list')

    return render(request, 'payments/invoice.html', {
        'order': order,
        'course': order.course,
        'student': order.user,
        'instructor': order.course.instructor,
    })


@login_required
def student_order_history(request):
    """
    Lists past orders and invoices for the logged in student.
    """
    orders = Order.objects.filter(
        user=request.user
    ).select_related('course').order_by('-created_at')

    return render(request, 'payments/order_history.html', {
        'orders': orders,
    })
