from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CourseForm
from .models import Category, Course, CoursePrerequisite, CourseReview, Module, Wishlist


def course_list(request):
    """List all published courses with search, category, level, and price filters."""
    queryset = (
        Course.objects.filter(status=Course.Status.PUBLISHED)
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
    if request.user.is_authenticated:
        user_wishlist = set(
            Wishlist.objects.filter(student=request.user).values_list('course_id', flat=True)
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
            'user_wishlist': user_wishlist,
        },
    )


def course_detail(request, slug):
    """Show detailed course overview, curriculum accordions, rating breakdown, and prerequisites."""
    course = get_object_or_404(
        Course.objects.select_related('instructor', 'category'),
        slug=slug,
    )

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
    is_in_wishlist = False
    prereqs_satisfied = True
    unmet_prereqs = []

    if request.user.is_authenticated:
        is_enrolled = course.enrollments.filter(student=request.user).exists()
        is_in_wishlist = Wishlist.objects.filter(student=request.user, course=course).exists()

        # Check prerequisites status for current user
        for p in course.prerequisite_requirements.select_related('required_course').all():
            has_passed = request.user.enrollments.filter(course=p.required_course, is_completed=True).exists()
            if not has_passed:
                prereqs_satisfied = False
                unmet_prereqs.append(p.required_course)

    prerequisites = course.prerequisite_requirements.select_related('required_course').all()

    return render(
        request,
        'courses/course_detail.html',
        {
            'course': course,
            'modules': modules,
            'standalone_lessons': standalone_lessons,
            'standalone_quizzes': standalone_quizzes,
            'is_enrolled': is_enrolled,
            'is_in_wishlist': is_in_wishlist,
            'reviews': reviews[:10],
            'reviews_count': reviews_count,
            'avg_rating': round(avg_rating, 1),
            'rating_breakdown': rating_breakdown,
            'prerequisites': prerequisites,
            'prereqs_satisfied': prereqs_satisfied,
            'unmet_prereqs': unmet_prereqs,
        },
    )


@login_required
@require_POST
def add_course_review(request, slug):
    """Submit a rating and review for a course."""
    course = get_object_or_404(Course, slug=slug)
    # Only enrolled students can review
    if not course.enrollments.filter(student=request.user).exists() and not request.user.is_staff:
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
    """Create a new course (instructors only)."""
    if not (request.user.is_instructor or request.user.is_staff or getattr(request.user, 'is_admin', False)):
        messages.error(request, "Instructor privileges required to create courses.")
        return redirect('courses:course_list')

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
    """Update an existing course (owner only)."""
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Course details updated.")
            return redirect('courses:course_detail', slug=course.slug)
    else:
        form = CourseForm(instance=course)
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Update Course'})


@login_required
def course_delete(request, slug):
    """Delete a course (owner only)."""
    course = get_object_or_404(Course, slug=slug, instructor=request.user)
    if request.method == 'POST':
        course.delete()
        messages.info(request, "Course deleted successfully.")
        return redirect('courses:course_list')
    return render(request, 'courses/course_confirm_delete.html', {'course': course})
