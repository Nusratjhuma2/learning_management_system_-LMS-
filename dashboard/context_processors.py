from django.db.models import Count
from courses.models import Announcement, Category
from accounts.signals import get_client_ip

def lms_stats_processor(request):
    """Context processor providing notifications, global announcements, and course categories to all templates."""
    context = {}
    context['sidebar_categories'] = Category.objects.annotate(courses_count=Count('courses')).order_by('name')
    context['client_ip'] = get_client_ip(request) or '127.0.0.1'
    if request.user.is_authenticated:
        # Latest global announcement
        context['global_announcements'] = Announcement.objects.filter(course__isnull=True)[:2]
    return context
