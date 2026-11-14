from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.db.models import Sum, Count, Avg
from django.shortcuts import get_object_or_404, redirect, render
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
    if request.user.is_superuser or request.user.is_staff or role == 'admin':
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
    if not (request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Administrative privileges required.")
        return redirect('dashboard:student_dashboard')

    total_users = User.objects.count()
    total_enrollments = Enrollment.objects.count()
    total_certificates = Certificate.objects.count()
    revenue_agg = Order.objects.filter(status=Order.Status.COMPLETED).aggregate(total_vol=Sum('final_amount'))
    total_volume = revenue_agg['total_vol'] or 0

    # Live Security Feed
    security_logs = SecurityAuditLog.objects.select_related('user').order_by('-created_at')[:40]

    # Active Sessions
    active_sessions = ActiveUserSession.objects.select_related('user').order_by('-updated_at')[:25]

    return render(request, 'dashboard/admin_dashboard.html', {
        'total_users': total_users,
        'total_enrollments': total_enrollments,
        'total_certificates': total_certificates,
        'total_volume': total_volume,
        'security_logs': security_logs,
        'active_sessions': active_sessions,
    })


@login_required
@require_POST
def terminate_session(request, session_pk):
    """Terminates an active session from the admin console."""
    if not (request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
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
