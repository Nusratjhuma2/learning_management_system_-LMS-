"""Centralized role and ownership authorization helpers for the LMS."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


def is_admin_user(user):
    """Return True if the authenticated user holds platform administrator privileges."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    role = (getattr(user, 'role', '') or '').strip().lower()
    return bool(getattr(user, 'is_superuser', False) or role == 'admin')


def is_instructor_user(user):
    """Return True if the authenticated user is a non-admin instructor."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if is_admin_user(user):
        return False
    role = (getattr(user, 'role', '') or '').strip().lower()
    return role == 'instructor'


def is_student_user(user):
    """Return True if the authenticated user is a student learner."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return not is_admin_user(user) and not is_instructor_user(user)


def is_course_manager(user, course):
    """Return True if user owns `course` as its instructor or is a platform admin."""
    if not user or not getattr(user, 'is_authenticated', False) or course is None:
        return False
    if is_admin_user(user):
        return True
    return is_instructor_user(user) and course.instructor_id == user.id


def get_dashboard_url_name(user):
    """Return the canonical dashboard URL name for the user's role."""
    if is_admin_user(user):
        return 'dashboard:admin_dashboard'
    if is_instructor_user(user):
        return 'dashboard:instructor_dashboard'
    return 'dashboard:student_dashboard'


def deny_role_redirect(request, message, redirect_to=None, **redirect_kwargs):
    """Flash an authorization error message and redirect to a role-appropriate page."""
    messages.error(request, message)
    if redirect_to:
        return redirect(redirect_to, **redirect_kwargs)
    return redirect(get_dashboard_url_name(request.user))


def deny_json(message='Permission denied.', status=403):
    """Return a consistent JSON authorization error response."""
    return JsonResponse({'status': 'forbidden', 'message': message}, status=status)
