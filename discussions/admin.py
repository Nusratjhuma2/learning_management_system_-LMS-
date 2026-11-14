from django.contrib import admin
from .models import CourseAnnouncement, DiscussionReply, DiscussionThread, Notification


class DiscussionReplyInline(admin.TabularInline):
    model = DiscussionReply
    extra = 0


@admin.register(DiscussionThread)
class DiscussionThreadAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'author', 'is_resolved', 'created_at']
    list_filter = ['course', 'is_resolved', 'created_at']
    search_fields = ['title', 'content', 'author__username']
    inlines = [DiscussionReplyInline]
    actions = ['mark_as_resolved', 'mark_as_unresolved']

    @admin.action(description="Mark selected threads as resolved")
    def mark_as_resolved(self, request, queryset):
        count = queryset.update(is_resolved=True)
        self.message_user(request, f"Marked {count} thread(s) as resolved.")

    @admin.action(description="Mark selected threads as unresolved")
    def mark_as_unresolved(self, request, queryset):
        count = queryset.update(is_resolved=False)
        self.message_user(request, f"Marked {count} thread(s) as unresolved.")


@admin.register(DiscussionReply)
class DiscussionReplyAdmin(admin.ModelAdmin):
    list_display = ['thread', 'author', 'created_at']
    list_filter = ['created_at']
    search_fields = ['content', 'author__username', 'thread__title']


@admin.register(CourseAnnouncement)
class CourseAnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'instructor', 'created_at']
    list_filter = ['course', 'created_at']
    search_fields = ['title', 'content', 'instructor__username']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['recipient__username', 'title']
    actions = ['mark_as_read']

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request, queryset):
        count = queryset.update(is_read=True)
        self.message_user(request, f"Marked {count} notification(s) as read.")
