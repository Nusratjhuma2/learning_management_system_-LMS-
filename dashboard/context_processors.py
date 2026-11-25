from django.db.models import Count
from accounts.permissions import is_student_user
from courses.models import Announcement, Category, Wishlist
from discussions.models import Notification
from accounts.signals import get_client_ip
from dashboard.themes import ROLE_THEMES, get_role_theme


def lms_stats_processor(request):
    """Context processor providing theme tokens, notifications, global announcements, and course categories."""
    user = getattr(request, 'user', None)
    active_role_key, role_theme = get_role_theme(user)
    context = {
        'active_role_key': active_role_key,
        'role_theme': role_theme,
        'role_themes': ROLE_THEMES,
        'sidebar_categories': Category.objects.annotate(courses_count=Count('courses')).order_by('name'),
        'client_ip': get_client_ip(request) or '127.0.0.1',
    }
    if user and user.is_authenticated:
        context['global_announcements'] = Announcement.objects.filter(course__isnull=True)[:2]
        context['unread_notifications_count'] = Notification.objects.filter(recipient=user, is_read=False).count()
        context['wishlist_count'] = Wishlist.objects.filter(student=user).count() if is_student_user(user) else 0
    return context
