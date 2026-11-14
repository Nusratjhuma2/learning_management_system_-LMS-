from courses.models import Announcement

def lms_stats_processor(request):
    """Context processor providing notifications or global announcements to all templates."""
    context = {}
    if request.user.is_authenticated:
        # Latest global announcement
        context['global_announcements'] = Announcement.objects.filter(course__isnull=True)[:2]
    return context
