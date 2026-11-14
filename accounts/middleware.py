from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from .models import ActiveUserSession, SecurityAuditLog


class SingleSessionEnforcementMiddleware:
    """Middleware enforcing single active login per user and invalidating concurrent sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow logout and login paths to proceed without interception
        try:
            login_url = reverse('accounts:login')
            logout_url = reverse('accounts:logout')
            if request.path in [login_url, logout_url]:
                return self.get_response(request)
        except Exception:
            pass

        if request.user.is_authenticated:
            try:
                active_session = request.user.active_session
            except (ActiveUserSession.DoesNotExist, AttributeError):
                active_session = None

            if active_session:
                if active_session.session_key != request.session.session_key:
                    logout(request)
                    messages.error(
                        request,
                        "Your account was signed in on another device. Only one active login is permitted.",
                    )
                    return redirect('accounts:login')
            else:
                # Attach an active session for the authenticated user if missing
                if request.session.session_key:
                    ActiveUserSession.objects.create(
                        user=request.user,
                        session_key=request.session.session_key,
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
        else:
            # Check if this unauthenticated request carried a session cookie that was just kicked
            cookie_key = request.COOKIES.get(getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid'))
            if cookie_key:
                kicked = SecurityAuditLog.objects.filter(
                    event_type=SecurityAuditLog.EventType.CONCURRENT_LOGIN_KICKED,
                    details__previous_session_key=cookie_key,
                ).exists()
                if kicked:
                    messages.error(
                        request,
                        "Your account was signed in on another device. Only one active login is permitted.",
                    )
                    response = redirect('accounts:login')
                    response.delete_cookie(getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid'))
                    return response

        return self.get_response(request)
