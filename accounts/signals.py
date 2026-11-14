from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .models import ActiveUserSession, SecurityAuditLog, TrustedDevice


def get_client_ip(request):
    """Safely extract client IP from request headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@receiver(user_logged_in)
def handle_user_login(sender, request, user, **kwargs):
    """Enforce single active user session and maintain security audit log and trusted devices."""
    if not request:
        return

    # Ensure session is saved to have a valid session_key
    if not request.session.session_key:
        request.session.save()

    new_session_key = request.session.session_key
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    device_fingerprint = (
        request.POST.get('device_fingerprint', '')
        or request.headers.get('X-Device-Fingerprint', '')
        or ''
    ).strip()

    # Track trusted devices if fingerprint is available
    if device_fingerprint:
        trusted = TrustedDevice.objects.filter(user=user, device_fingerprint=device_fingerprint).first()
        if trusted:
            trusted.ip_address = ip_address
            trusted.user_agent = user_agent
            trusted.save(update_fields=['ip_address', 'user_agent', 'last_used_at'])
        else:
            # Enforce max_devices limit by pruning oldest trusted devices if needed
            current_count = user.trusted_devices.count()
            if current_count >= user.max_devices:
                excess = current_count - user.max_devices + 1
                oldest_ids = list(
                    user.trusted_devices.order_by('last_used_at').values_list('id', flat=True)[:excess]
                )
                TrustedDevice.objects.filter(id__in=oldest_ids).delete()

            TrustedDevice.objects.create(
                user=user,
                device_fingerprint=device_fingerprint,
                device_name=f"Device {user.trusted_devices.count() + 1}",
                ip_address=ip_address,
                user_agent=user_agent,
            )

    # Check and enforce ActiveUserSession
    try:
        active_session = user.active_session
        if active_session.session_key != new_session_key:
            old_session_key = active_session.session_key
            # Invalidate the old Django session in database
            try:
                Session.objects.filter(session_key=old_session_key).delete()
            except Exception:
                pass

            # Log concurrent login kick event
            SecurityAuditLog.objects.create(
                user=user,
                event_type=SecurityAuditLog.EventType.CONCURRENT_LOGIN_KICKED,
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    'previous_session_key': old_session_key,
                    'new_session_key': new_session_key,
                    'device_fingerprint': device_fingerprint,
                },
            )

            active_session.session_key = new_session_key
            active_session.ip_address = ip_address
            active_session.user_agent = user_agent
            if device_fingerprint:
                active_session.device_fingerprint = device_fingerprint
            active_session.save()
        else:
            # Same session key, refresh IP and User-Agent
            active_session.ip_address = ip_address
            active_session.user_agent = user_agent
            if device_fingerprint:
                active_session.device_fingerprint = device_fingerprint
            active_session.save()

    except ActiveUserSession.DoesNotExist:
        ActiveUserSession.objects.create(
            user=user,
            session_key=new_session_key,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
        )
