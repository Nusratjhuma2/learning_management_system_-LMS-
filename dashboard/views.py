import json
import datetime
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ActiveUserSession, SecurityAuditLog, TrustedDevice
from assignments.models import Assignment, AssignmentSubmission
from courses.models import Course
from discussions.models import DiscussionThread
from enrollments.models import Certificate, Enrollment, StudentBadge
from payments.models import Order
from quizzes.models import Quiz, QuizAttempt

User = get_user_model()


@login_required
def dashboard_router(request):
    """Dispatches the user to their designated dashboard view based on account role."""
    role = getattr(request.user, 'role', 'student')
    if request.user.is_superuser or role == 'admin':
        return redirect('dashboard:admin_dashboard')
    elif role == 'instructor':
        return redirect('dashboard:instructor_dashboard')
    else:
        return redirect('dashboard:student_dashboard')


@login_required
def student_dashboard(request):
    """
    Candidate & Student Command Center.
    Curriculum progress, resume study buttons, certificates, security sessions, and badges.
    """
    user = request.user
    enrollments = Enrollment.objects.filter(
        student=user
    ).select_related('course', 'course__instructor').prefetch_related('course__lessons')

    certificates = Certificate.objects.filter(
        enrollment__student=user
    ).select_related('enrollment__course')

    badges = StudentBadge.objects.filter(student=user).select_related('badge')

    recent_attempts = QuizAttempt.objects.filter(student=user).select_related('quiz', 'quiz__course')[:5]
    recent_submissions = AssignmentSubmission.objects.filter(student=user).select_related('assignment', 'assignment__course')[:5]

    active_session = getattr(user, 'active_session', None)
    trusted_devices = TrustedDevice.objects.filter(user=user)[:5]

    return render(request, 'dashboard/student_dashboard.html', {
        'user': user,
        'enrollments': enrollments,
        'certificates': certificates,
        'badges': badges,
        'recent_attempts': recent_attempts,
        'recent_submissions': recent_submissions,
        'active_session': active_session,
        'trusted_devices': trusted_devices,
    })


@login_required
def instructor_dashboard(request):
    """
    Instructor Studio & Grading Command Center.
    Course metrics, student enrollments, assignment grading queue, and student Q&A.
    """
    if not (request.user.role == 'instructor' or request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access restricted to instructors.")
        return redirect('dashboard:student_dashboard')

    courses = Course.objects.filter(instructor=request.user).annotate(
        student_count=Count('enrollments')
    )

    # Pending grading queue
    pending_submissions = AssignmentSubmission.objects.filter(
        assignment__course__instructor=request.user,
        status=AssignmentSubmission.Status.SUBMITTED,
    ).select_related('assignment', 'student', 'assignment__course')[:10]

    # Revenue generated
    revenue_agg = Order.objects.filter(
        course__instructor=request.user,
        status=Order.Status.COMPLETED,
    ).aggregate(total_revenue=Sum('final_amount'))
    total_revenue = revenue_agg['total_revenue'] or 0

    # Unresolved discussion questions
    unresolved_questions = DiscussionThread.objects.filter(
        course__instructor=request.user,
        is_resolved=False,
    ).select_related('author', 'course')[:5]

    # Quiz performance across instructor courses
    recent_quiz_attempts = QuizAttempt.objects.filter(
        quiz__course__instructor=request.user
    ).select_related('quiz', 'student')[:10]

    return render(request, 'dashboard/instructor_dashboard.html', {
        'courses': courses,
        'pending_submissions': pending_submissions,
        'total_revenue': total_revenue,
        'unresolved_questions': unresolved_questions,
        'recent_quiz_attempts': recent_quiz_attempts,
    })


@login_required
def admin_dashboard(request):
    """
    Executive Security & Platform Operations Console.
    Real-time security audit log stream, active session management, platform metrics.
    """
    if not (request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Administrative privileges required.")
        return redirect('dashboard:instructor_dashboard' if getattr(request.user, 'role', '') == 'instructor' else 'dashboard:student_dashboard')

    total_users = User.objects.count()
    total_enrollments = Enrollment.objects.count()
    total_certificates = Certificate.objects.count()
    revenue_agg = Order.objects.filter(status=Order.Status.COMPLETED).aggregate(total_vol=Sum('final_amount'))
    total_volume = revenue_agg['total_vol'] or 0

    # Live Security Feed
    security_logs = SecurityAuditLog.objects.select_related('user').order_by('-created_at')[:40]

    # Active Sessions
    active_sessions = ActiveUserSession.objects.select_related('user').order_by('-updated_at')[:25]

    # --- Additional KPIs ---
    total_courses = Course.objects.count()
    total_instructors = User.objects.filter(role='instructor').count()
    total_students = User.objects.filter(role='student').count()
    active_courses = Course.objects.filter(status='published').count()
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    total_quizzes = Quiz.objects.count()
    total_assignments = Assignment.objects.count()
    avg_quiz_score = QuizAttempt.objects.aggregate(avg=Avg('score'))['avg'] or 0
    completed_enrollments = Enrollment.objects.filter(is_completed=True).count()
    completion_rate = round((completed_enrollments / total_enrollments * 100), 1) if total_enrollments > 0 else 0

    # --- Monthly Trends (last 6 continuous months) ---
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_enrollments = (
        Enrollment.objects.filter(enrolled_at__gte=six_months_ago)
        .annotate(month=TruncMonth('enrolled_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    monthly_revenue = (
        Order.objects.filter(status=Order.Status.COMPLETED, created_at__gte=six_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('final_amount'))
        .order_by('month')
    )

    now = timezone.now()
    six_months = []
    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        six_months.append((year, month, datetime.date(year, month, 1).strftime('%b %Y')))

    enroll_map = {}
    for m in monthly_enrollments:
        if m['month']:
            enroll_map[(m['month'].year, m['month'].month)] = m['count']

    rev_map = {}
    for m in monthly_revenue:
        if m['month']:
            rev_map[(m['month'].year, m['month'].month)] = float(m['total'] or 0)

    enrollment_chart_labels = json.dumps([label for _, _, label in six_months])
    enrollment_chart_data = json.dumps([enroll_map.get((y, m), 0) for y, m, _ in six_months])
    revenue_chart_labels = json.dumps([label for _, _, label in six_months])
    revenue_chart_data = json.dumps([rev_map.get((y, m), 0.0) for y, m, _ in six_months])

    # --- Course Status Distribution (pie chart) ---
    course_status_dist = Course.objects.values('status').annotate(count=Count('id'))
    status_dict = {s['status']: s['count'] for s in course_status_dist}
    course_status_labels = json.dumps(['Published', 'Draft', 'Archived'])
    course_status_data = json.dumps([
        status_dict.get('published', 0),
        status_dict.get('draft', 0),
        status_dict.get('archived', 0)
    ])

    # --- User Role Distribution (pie chart) ---
    user_role_dist = User.objects.values('role').annotate(count=Count('id'))
    role_dict = {r['role']: r['count'] for r in user_role_dist}
    role_labels = json.dumps(['Students', 'Instructors', 'Administrators'])
    role_data = json.dumps([
        role_dict.get('student', 0),
        role_dict.get('instructor', 0),
        role_dict.get('admin', 0)
    ])

    # --- All Courses for Admin Governance & Moderation ---
    all_courses = Course.objects.annotate(
        enrollment_count=Count('enrollments')
    ).select_related('instructor', 'category').order_by('-created_at')

    # --- Top 5 Courses by Enrollment ---
    top_courses = Course.objects.annotate(
        enrollment_count=Count('enrollments')
    ).select_related('instructor').order_by('-enrollment_count')[:5]

    # --- Recent Orders (last 10) ---
    recent_orders = Order.objects.select_related('user', 'course').order_by('-created_at')[:10]

    return render(request, 'dashboard/admin_dashboard.html', {
        'total_users': total_users,
        'total_enrollments': total_enrollments,
        'total_certificates': total_certificates,
        'total_volume': total_volume,
        'security_logs': security_logs,
        'active_sessions': active_sessions,
        'all_courses': all_courses,
        # New KPIs
        'total_courses': total_courses,
        'total_instructors': total_instructors,
        'total_students': total_students,
        'active_courses': active_courses,
        'pending_orders': pending_orders,
        'total_quizzes': total_quizzes,
        'total_assignments': total_assignments,
        'avg_quiz_score': avg_quiz_score,
        'completed_enrollments': completed_enrollments,
        'completion_rate': completion_rate,
        # Chart data
        'enrollment_chart_labels': enrollment_chart_labels,
        'enrollment_chart_data': enrollment_chart_data,
        'revenue_chart_labels': revenue_chart_labels,
        'revenue_chart_data': revenue_chart_data,
        'course_status_labels': course_status_labels,
        'course_status_data': course_status_data,
        'role_labels': role_labels,
        'role_data': role_data,
        # Tables
        'top_courses': top_courses,
        'recent_orders': recent_orders,
    })


@login_required
@require_POST
def terminate_session(request, session_pk):
    """Terminates an active session from the admin console."""
    if not (request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Permission denied.")
        return redirect('dashboard:admin_dashboard')

    active_sess = get_object_or_404(ActiveUserSession, pk=session_pk)
    target_user = active_sess.user
    key = active_sess.session_key

    # Delete Django session
    Session.objects.filter(session_key=key).delete()
    active_sess.delete()

    # Log action
    SecurityAuditLog.objects.create(
        user=target_user,
        event_type=SecurityAuditLog.EventType.CONCURRENT_LOGIN_KICKED,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        details={'terminated_by_admin': request.user.username, 'session_key': key},
    )

    messages.success(request, f"Active session for user '{target_user.username}' was forcefully terminated.")
    return redirect('dashboard:admin_dashboard')



@login_required
def admin_dashboard_api(request):
    """JSON API for admin dashboard real-time data refresh."""
    if not (request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    total_enrollments = Enrollment.objects.count()
    completed = Enrollment.objects.filter(is_completed=True).count()
    completion_rate = round((completed / total_enrollments * 100), 1) if total_enrollments > 0 else 0
    revenue_agg = Order.objects.filter(status=Order.Status.COMPLETED).aggregate(total_vol=Sum('final_amount'))
    total_volume = float(revenue_agg['total_vol'] or 0)

    data = {
        'total_users': User.objects.count(),
        'total_students': User.objects.filter(role='student').count(),
        'total_instructors': User.objects.filter(role='instructor').count(),
        'total_enrollments': total_enrollments,
        'total_certificates': Certificate.objects.count(),
        'total_courses': Course.objects.count(),
        'active_courses': Course.objects.filter(status='published').count(),
        'pending_orders': Order.objects.filter(status=Order.Status.PENDING).count(),
        'total_volume': total_volume,
        'completion_rate': completion_rate,
        'active_sessions': ActiveUserSession.objects.count(),
    }
    return JsonResponse(data)
