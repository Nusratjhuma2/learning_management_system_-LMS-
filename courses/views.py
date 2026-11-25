from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import (
    deny_role_redirect,
    is_admin_user,
    is_course_manager,
    is_instructor_user,
    is_student_user,
)
from enrollments.models import Enrollment
from payments.models import Order
from .forms import CourseForm
from .models import Category, Course, CoursePrerequisite, CourseReview, Module, Wishlist
from .services.curriculum import build_course_curriculum_state


def _get_purchased_or_enrolled_course_ids(user):
    """Return set of course IDs the authenticated student owns via enrollment or completed order."""
    if not is_student_user(user):
        return set()
    enrolled_ids = set(
        Enrollment.objects.filter(student=user).values_list('course_id', flat=True)
    )
    ordered_ids = set(
        Order.objects.filter(user=user, status=Order.Status.COMPLETED).values_list('course_id', flat=True)
    )
    return enrolled_ids | ordered_ids


def course_suggest(request):
    """Return JSON autocomplete suggestions for course search."""
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'suggestions': []})
    matches = (
        Course.objects.filter(
            Q(status=Course.Status.PUBLISHED, is_blocked=False) &
            (
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(what_you_will_learn__icontains=q) |
                Q(instructor__username__icontains=q) |
                Q(instructor__first_name__icontains=q) |
                Q(instructor__last_name__icontains=q) |
                Q(category__name__icontains=q)
            )
        )
        .select_related('instructor', 'category')
        .order_by('title')[:8]
    )
    owned_course_ids = _get_purchased_or_enrolled_course_ids(request.user)
    suggestions = []
    for c in matches:
        is_enrolled = c.id in owned_course_ids
        suggestions.append({
            'title': c.title,
            'slug': c.slug,
            'category': c.category.name if c.category else '',
            'level': c.get_level_display(),
            'instructor': c.instructor.get_full_name() or c.instructor.username,
            'thumbnail': c.get_thumbnail_url or '',
            'price': None if is_enrolled else str(c.effective_price),
            'is_free': False if is_enrolled else c.is_free,
            'is_enrolled': is_enrolled,
            'url': f'/courses/{c.slug}/',
        })
    return JsonResponse({'suggestions': suggestions})


def course_list(request):
    """List all published courses with search, category, level, and price filters. Admins can view blocked courses."""
    is_admin = is_admin_user(request.user)
    is_instructor = is_instructor_user(request.user)
    is_student = is_student_user(request.user)

    if is_admin:
        queryset = (
            Course.objects.all()
            .select_related('instructor', 'category')
            .annotate(annotated_rating=Avg('reviews__rating'), reviews_total=Count('reviews'))
        )
    else:
        queryset = (
            Course.objects.filter(status=Course.Status.PUBLISHED, is_blocked=False)
            .select_related('instructor', 'category')
            .annotate(annotated_rating=Avg('reviews__rating'), reviews_total=Count('reviews'))
        )

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(instructor__username__icontains=q)
            | Q(instructor__first_name__icontains=q)
            | Q(instructor__last_name__icontains=q)
        )

    # Category filter
    category_slug = request.GET.get('category', '').strip()
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)

    # Level filter
    level = request.GET.get('level', '').strip()
    if level and level in Course.Level.values:
        queryset = queryset.filter(level=level)

    # Price filter
    price_filter = request.GET.get('price', '').strip()
    if price_filter == 'free':
        queryset = queryset.filter(is_free=True)
    elif price_filter == 'paid':
        queryset = queryset.filter(is_free=False)

    # Saved wishlist filter (students only)
    wishlist_only = is_student and request.GET.get('wishlist', '').strip() == '1'
    if wishlist_only:
        wishlist_ids = Wishlist.objects.filter(student=request.user).values_list('course_id', flat=True)
        queryset = queryset.filter(id__in=wishlist_ids)

    # Sorting
    sort = request.GET.get('sort', 'newest')
    if sort == 'rating':
        queryset = queryset.order_by('-annotated_rating', '-created_at')
    elif sort == 'price_low':
        queryset = queryset.order_by('price')
    elif sort == 'price_high':
        queryset = queryset.order_by('-price')
    else:
        queryset = queryset.order_by('-created_at')

    categories = Category.objects.annotate(courses_count=Count('courses')).filter(courses_count__gt=0)

    user_wishlist = set()
    enrolled_course_ids = set()
    if is_student:
        user_wishlist = set(
            Wishlist.objects.filter(student=request.user).values_list('course_id', flat=True)
        )
        enrolled_course_ids = _get_purchased_or_enrolled_course_ids(request.user)

    # Promotional carousel: top courses by rating + enrollment count (up to 6 slides)
    promo_courses = []
    if not wishlist_only:
        promo_courses = list(
            Course.objects.filter(status=Course.Status.PUBLISHED, is_blocked=False)
            .select_related('instructor', 'category')
            .annotate(
                avg_r=Avg('reviews__rating'),
                rev_count=Count('reviews', distinct=True),
                enroll_count=Count('enrollments', distinct=True),
                lesson_count=Count('lessons', distinct=True),
            )
            .order_by('-avg_r', '-enroll_count', '-created_at')[:6]
        )

    return render(
        request,
        'courses/course_list.html',
        {
            'courses': queryset,
            'categories': categories,
            'search_query': q,
            'current_category': category_slug,
            'current_level': level,
            'current_price': price_filter,
            'current_sort': sort,
            'wishlist_only': wishlist_only,
            'user_wishlist': user_wishlist,
            'enrolled_course_ids': enrolled_course_ids,
            'promo_courses': promo_courses,
            'is_admin': is_admin,
            'is_instructor': is_instructor,
            'is_student': is_student,
            'can_create_course': is_instructor or is_admin,
        },
    )


def course_detail(request, slug):
    """Show detailed course overview, curriculum accordions, rating breakdown, and prerequisites."""
    course = get_object_or_404(
        Course.objects.select_related('instructor', 'category'),
        slug=slug,
    )
    is_admin = is_admin_user(request.user)
    is_instructor = is_instructor_user(request.user)
    is_student = is_student_user(request.user)
    can_manage_course = is_course_manager(request.user, course)

    if course.is_blocked and not is_admin:
        messages.error(request, "This course has been suspended or blocked by platform administration.")
        return redirect('courses:course_list')

    modules = (
        course.modules.prefetch_related('lessons', 'quizzes')
        .order_by('order', 'id')
    )
    standalone_lessons = course.lessons.filter(module__isnull=True).order_by('order', 'id')
    standalone_quizzes = course.quizzes.filter(module__isnull=True).order_by('created_at')

    reviews = course.reviews.select_related('student').order_by('-created_at')
    reviews_count = reviews.count()
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0.0

    # Rating distribution breakdown (5 stars to 1 star)
    rating_breakdown = {}
    for r in range(5, 0, -1):
        count_r = reviews.filter(rating=r).count()
        percent_r = int((count_r / reviews_count * 100) if reviews_count > 0 else 0)
        rating_breakdown[r] = {'count': count_r, 'percent': percent_r}

    is_enrolled = False
    has_purchased = False
    is_in_wishlist = False
    prereqs_satisfied = True
    unmet_prereqs = []

    if is_student:
        is_enrolled = course.enrollments.filter(student=request.user).exists()
        has_purchased = is_enrolled or Order.objects.filter(
            user=request.user, course=course, status=Order.Status.COMPLETED
        ).exists()
        is_in_wishlist = Wishlist.objects.filter(student=request.user, course=course).exists()

        # Check prerequisites status for current student
        for p in course.prerequisite_requirements.select_related('required_course').all():
            has_passed = request.user.enrollments.filter(course=p.required_course, is_completed=True).exists()
            if not has_passed:
                prereqs_satisfied = False
                unmet_prereqs.append(p.required_course)

    prerequisites = course.prerequisite_requirements.select_related('required_course').all()
    curriculum = build_course_curriculum_state(course, request.user)
    next_module_order = (modules.aggregate(max_order=Max('order'))['max_order'] or 0) + 1

    return render(
        request,
        'courses/course_detail.html',
        {
            'course': course,
            'modules': modules,
            'standalone_lessons': standalone_lessons,
            'standalone_quizzes': standalone_quizzes,
            'curriculum': curriculum,
            'next_module_order': next_module_order,
            'is_enrolled': is_enrolled,
            'has_purchased': has_purchased,
            'is_in_wishlist': is_in_wishlist,
            'reviews': reviews[:10],
            'reviews_count': reviews_count,
            'avg_rating': round(avg_rating, 1),
            'rating_breakdown': rating_breakdown,
            'prerequisites': prerequisites,
            'prereqs_satisfied': prereqs_satisfied,
            'unmet_prereqs': unmet_prereqs,
            'is_admin': is_admin,
            'is_instructor': is_instructor,
            'is_student': is_student,
            'can_manage_course': can_manage_course,
        },
    )


@login_required
@require_POST
def module_create(request, slug):
    """Add a new structured curriculum module to a course (author or admin)."""
    course = get_object_or_404(Course, slug=slug)
    if not is_course_manager(request.user, course):
        return deny_role_redirect(
            request,
            "Permission denied. Only the course instructor or an administrator can add modules.",
            'courses:course_detail',
            slug=course.slug,
        )

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    raw_order = request.POST.get('order', '').strip()

    if not title:
        messages.error(request, "Module title is required.")
        return redirect('courses:course_detail', slug=course.slug)

    max_order = course.modules.aggregate(max_order=Max('order'))['max_order'] or 0
    try:
        order = int(raw_order) if raw_order else (max_order + 1)
    except (ValueError, TypeError):
        order = max_order + 1

    if course.modules.filter(order=order).exists():
        order = max_order + 1

    Module.objects.create(
        course=course,
        title=title,
        description=description,
        order=max(order, 1),
    )
    messages.success(request, f"Module '{title}' added to curriculum.")
    return redirect('courses:course_detail', slug=course.slug)


@login_required
@require_POST
def add_course_review(request, slug):
    """Submit a rating and review for a course (enrolled students only)."""
    course = get_object_or_404(Course, slug=slug)
    if not is_student_user(request.user):
        return deny_role_redirect(
            request,
            "Only enrolled students can submit course reviews.",
            'courses:course_detail',
            slug=slug,
        )
    if not course.enrollments.filter(student=request.user).exists():
        messages.error(request, "Only students enrolled in this course can post a review.")
        return redirect('courses:course_detail', slug=slug)

    try:
        rating = int(request.POST.get('rating', 5))
        rating = min(max(rating, 1), 5)
    except (ValueError, TypeError):
        rating = 5

    comment = request.POST.get('comment', '').strip()
    CourseReview.objects.update_or_create(
        course=course,
        student=request.user,
        defaults={'rating': rating, 'comment': comment},
    )
    messages.success(request, "Thank you! Your course review has been saved.")
    return redirect('courses:course_detail', slug=slug)


@login_required
@require_POST
def toggle_wishlist(request, slug):
    """Add or remove course from student's wishlist."""
    course = get_object_or_404(Course, slug=slug)
    if not is_student_user(request.user):
        return deny_role_redirect(
            request,
            "Only student accounts can save courses to a wishlist.",
            'courses:course_detail',
            slug=slug,
        )
    item = Wishlist.objects.filter(student=request.user, course=course).first()
    if item:
        item.delete()
        messages.info(request, f"Removed '{course.title}' from your wishlist.")
    else:
        Wishlist.objects.create(student=request.user, course=course)
        messages.success(request, f"Saved '{course.title}' to your wishlist.")
    return redirect('courses:course_detail', slug=slug)


@login_required
def course_create(request):
    """Create a new course (instructors or admins only)."""
    if not (is_instructor_user(request.user) or is_admin_user(request.user)):
        return deny_role_redirect(
            request,
            "Instructor privileges required to create courses.",
            'courses:course_list',
        )

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.save()
            messages.success(request, f"Course '{course.title}' successfully created.")
            return redirect('courses:course_detail', slug=course.slug)
    else:
        form = CourseForm()
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Create Course'})


@login_required
def course_update(request, slug):
    """Update an existing course (owner or platform administrator)."""
    course = get_object_or_404(Course, slug=slug)
    if not is_course_manager(request.user, course):
        return deny_role_redirect(
            request,
            "Permission denied. You can only edit courses you teach.",
            'courses:course_detail',
            slug=course.slug,
        )

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, f"Course '{course.title}' details updated.")
            return redirect('courses:course_detail', slug=course.slug)
    else:
        form = CourseForm(instance=course)
    return render(request, 'courses/course_form.html', {'form': form, 'title': f'Update Course: {course.title}'})


@login_required
def course_delete(request, slug):
    """Delete a course (owner or platform administrator can delete any course)."""
    course = get_object_or_404(Course, slug=slug)
    is_admin = is_admin_user(request.user)
    if not is_course_manager(request.user, course):
        return deny_role_redirect(
            request,
            "Permission denied. You can only delete courses you teach.",
            'courses:course_detail',
            slug=course.slug,
        )

    if request.method == 'POST':
        title = course.title
        course.delete()
        messages.info(request, f"Course '{title}' deleted successfully.")
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        if is_admin:
            return redirect('dashboard:admin_dashboard')
        return redirect('courses:course_list')
    return render(request, 'courses/course_confirm_delete.html', {'course': course, 'is_admin': is_admin})


@login_required
@require_POST
def toggle_course_block(request, slug):
    """Platform administrators can block or unblock any course from any instructor."""
    if not is_admin_user(request.user):
        return deny_role_redirect(
            request,
            "Administrative privileges required to block or unblock courses.",
            'courses:course_list',
        )

    course = get_object_or_404(Course, slug=slug)
    course.is_blocked = not course.is_blocked
    course.save()

    state = "BLOCKED" if course.is_blocked else "UNBLOCKED"
    messages.success(request, f"Course '{course.title}' has been {state} by administration.")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:admin_dashboard'
    return redirect(next_url)
