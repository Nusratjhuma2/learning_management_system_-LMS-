from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, models
from django.db.models import Avg, Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import Course, CourseReview
from enrollments.models import Enrollment
from .forms import ProfileUpdateForm, SignUpForm
from .models import User


def signup_view(request):
    """Handle user registration with robust duplicate prevention."""
    if request.user.is_authenticated:
        return redirect('courses:course_list')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user)
                messages.success(request, f"Welcome to LMS, {user.first_name or user.username}! Your account has been registered.")
                return redirect('courses:course_list')
            except IntegrityError:
                form.add_error('username', 'A user with this username already exists. Please choose another username.')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile_view(request):
    """Display and update user profile."""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, 'accounts/profile.html', {'form': form})


def instructor_list(request):
    """
    Public directory of all faculty members and course instructors.
    Allows students to browse instructor profiles, credentials, and courses taught.
    """
    instructors = (
        User.objects.filter(role=User.Role.INSTRUCTOR, is_active=True)
        .annotate(
            published_courses_count=Count(
                'courses_created',
                filter=Q(courses_created__status=Course.Status.PUBLISHED),
                distinct=True,
            ),
            total_students_enrolled=Count(
                'courses_created__enrollments',
                filter=Q(courses_created__status=Course.Status.PUBLISHED),
                distinct=True,
            ),
        )
        .prefetch_related(
            Prefetch(
                'courses_created',
                queryset=Course.objects.filter(status=Course.Status.PUBLISHED).select_related('category'),
                to_attr='published_courses'
            )
        )
        .order_by('-published_courses_count', 'first_name', 'username')
    )

    q = request.GET.get('q', '').strip()
    if q:
        instructors = instructors.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(username__icontains=q) |
            Q(institution_name__icontains=q) |
            Q(department__icontains=q) |
            Q(bio__icontains=q)
        )

    dept = request.GET.get('dept', '').strip()
    if dept:
        instructors = instructors.filter(department__iexact=dept)

    # Collect available departments for filter pills
    departments = (
        User.objects.filter(role=User.Role.INSTRUCTOR, is_active=True)
        .exclude(department='')
        .values_list('department', flat=True)
        .distinct()
    )

    total_instructors = instructors.count()
    total_courses = sum(inst.published_courses_count for inst in instructors)
    total_students = sum(inst.total_students_enrolled for inst in instructors)

    return render(request, 'accounts/instructor_list.html', {
        'instructors': instructors,
        'q': q,
        'selected_dept': dept,
        'departments': departments,
        'total_instructors': total_instructors,
        'total_courses': total_courses,
        'total_students': total_students,
    })


def instructor_detail(request, username):
    """
    Public profile page for a specific instructor.
    Shows faculty credentials, biography, and all authored courses.
    """
    instructor = get_object_or_404(
        User,
        username=username,
        role=User.Role.INSTRUCTOR,
        is_active=True,
    )

    courses = (
        Course.objects.filter(instructor=instructor, status=Course.Status.PUBLISHED)
        .select_related('category')
        .prefetch_related('lessons', 'enrollments')
        .order_by('-created_at')
    )

    total_courses = courses.count()
    total_students = (
        Enrollment.objects.filter(course__instructor=instructor)
        .values('student')
        .distinct()
        .count()
    )
    total_lessons = sum(c.lessons.count() for c in courses)

    reviews = (
        CourseReview.objects.filter(course__instructor=instructor)
        .select_related('student', 'course')
        .order_by('-created_at')[:10]
    )
    avg_rating = (
        CourseReview.objects.filter(course__instructor=instructor)
        .aggregate(avg=Avg('rating'))['avg'] or 5.0
    )

    enrolled_course_ids = set()
    if request.user.is_authenticated:
        enrolled_course_ids = set(
            Enrollment.objects.filter(student=request.user).values_list('course_id', flat=True)
        )

    return render(request, 'accounts/instructor_detail.html', {
        'instructor': instructor,
        'courses': courses,
        'total_courses': total_courses,
        'total_students': total_students,
        'total_lessons': total_lessons,
        'avg_rating': round(avg_rating, 1),
        'reviews': reviews,
        'enrolled_course_ids': enrolled_course_ids,
    })
