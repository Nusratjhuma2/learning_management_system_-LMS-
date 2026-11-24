import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.db import models
from courses.models import Course
from enrollments.models import Enrollment
from .forms import CouponForm
from .models import Coupon, Order, PaymentTransaction


@login_required
def checkout(request, course_slug):
    """
    Checkout portal for enrolling in paid courses.
    Supports coupon discounts, automatic zero-amount enrollment, and gateway selection.
    """
    course = get_object_or_404(Course, slug=course_slug, status=Course.Status.PUBLISHED)

    # If student is already enrolled or already bought the course
    already_enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    already_purchased = Order.objects.filter(
        user=request.user, course=course, status=Order.Status.COMPLETED
    ).exists()
    if already_enrolled or already_purchased:
        if already_purchased and not already_enrolled:
            Enrollment.objects.get_or_create(student=request.user, course=course)
        messages.info(request, f"You already own '{course.title}'.")
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
            is_valid, reason = coupon.is_valid(course=course)
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


def _is_coupon_admin(user):
    return user.is_authenticated and (getattr(user, 'is_admin', False) or user.is_staff or user.is_superuser)


def _is_coupon_instructor(user):
    return user.is_authenticated and (getattr(user, 'is_instructor', False) or getattr(user, 'role', '') == 'instructor')


def _can_manage_coupons(user):
    return _is_coupon_admin(user) or _is_coupon_instructor(user)


def _user_can_edit_coupon(user, coupon):
    if _is_coupon_admin(user):
        return True
    if coupon.created_by == user:
        return True
    if coupon.course and coupon.course.instructor == user:
        return True
    return False


@login_required
def coupon_list(request):
    """
    Promotional Coupon Management console.
    Instructors view coupons for their own courses; Admins view and manage all coupons.
    """
    if not _can_manage_coupons(request.user):
        messages.error(request, "Permission denied. Only instructors and administrators can manage coupons.")
        return redirect('dashboard:index')

    is_admin = _is_coupon_admin(request.user)

    if is_admin:
        coupons = Coupon.objects.select_related('course', 'course__instructor', 'created_by').all()
    else:
        coupons = Coupon.objects.select_related('course', 'created_by').filter(
            models.Q(created_by=request.user) | models.Q(course__instructor=request.user)
        ).distinct()

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        coupons = coupons.filter(
            models.Q(code__icontains=q) | models.Q(course__title__icontains=q)
        )

    # Status filter
    status_filter = request.GET.get('status', 'all')
    now = timezone.now()
    if status_filter == 'active':
        coupons = coupons.filter(is_active=True).filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
        ).filter(used_count__lt=models.F('max_uses'))
    elif status_filter == 'inactive':
        coupons = coupons.filter(is_active=False)
    elif status_filter == 'expired':
        coupons = coupons.filter(valid_until__lt=now)

    total_coupons = coupons.count()
    active_coupons = sum(1 for c in coupons if c.is_active and not c.is_expired and c.used_count < c.max_uses)
    total_redemptions = sum(c.used_count for c in coupons)

    return render(request, 'payments/coupon_list.html', {
        'coupons': coupons,
        'is_admin': is_admin,
        'q': q,
        'status_filter': status_filter,
        'total_coupons': total_coupons,
        'active_coupons': active_coupons,
        'total_redemptions': total_redemptions,
    })


@login_required
def coupon_create(request):
    """
    Creates a new promotional coupon.
    Instructors can assign to their own courses; Admins can create site-wide or course-specific coupons.
    """
    if not _can_manage_coupons(request.user):
        messages.error(request, "Permission denied.")
        return redirect('dashboard:index')

    is_admin = _is_coupon_admin(request.user)

    if request.method == 'POST':
        form = CouponForm(request.POST, user=request.user)
        if form.is_valid():
            coupon = form.save(commit=False)
            coupon.created_by = request.user
            coupon.save()
            messages.success(request, f"Coupon '{coupon.code}' created successfully!")
            return redirect('payments:coupon_list')
    else:
        initial = {'is_active': True, 'max_uses': 100, 'discount_percent': 20}
        course_id = request.GET.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
                if is_admin or course.instructor == request.user:
                    initial['course'] = course
            except Course.DoesNotExist:
                pass
        form = CouponForm(initial=initial, user=request.user)

    return render(request, 'payments/coupon_form.html', {
        'form': form,
        'is_edit': False,
        'is_admin': is_admin,
    })


@login_required
def coupon_edit(request, coupon_id):
    """
    Updates an existing promotional coupon.
    """
    coupon = get_object_or_404(Coupon.objects.select_related('course'), pk=coupon_id)
    if not _user_can_edit_coupon(request.user, coupon):
        messages.error(request, "Permission denied. You cannot edit this coupon.")
        return redirect('payments:coupon_list')

    is_admin = _is_coupon_admin(request.user)

    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Coupon '{coupon.code}' updated successfully.")
            return redirect('payments:coupon_list')
    else:
        form = CouponForm(instance=coupon, user=request.user)

    return render(request, 'payments/coupon_form.html', {
        'form': form,
        'coupon': coupon,
        'is_edit': True,
        'is_admin': is_admin,
    })


@login_required
@require_POST
def coupon_toggle_status(request, coupon_id):
    """
    Quickly toggles a coupon's is_active status.
    """
    coupon = get_object_or_404(Coupon.objects.select_related('course'), pk=coupon_id)
    if not _user_can_edit_coupon(request.user, coupon):
        messages.error(request, "Permission denied.")
        return redirect('payments:coupon_list')

    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=['is_active'])
    status_str = "activated" if coupon.is_active else "deactivated"
    messages.success(request, f"Coupon '{coupon.code}' has been {status_str}.")
    return redirect('payments:coupon_list')


@login_required
@require_POST
def coupon_delete(request, coupon_id):
    """
    Deletes a promotional coupon.
    """
    coupon = get_object_or_404(Coupon.objects.select_related('course'), pk=coupon_id)
    if not _user_can_edit_coupon(request.user, coupon):
        messages.error(request, "Permission denied.")
        return redirect('payments:coupon_list')

    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon '{code}' has been deleted.")
    return redirect('payments:coupon_list')
