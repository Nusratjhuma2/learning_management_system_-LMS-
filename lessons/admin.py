from django.contrib import admin

from .models import Lesson, LessonNote, LessonProgress


class LessonProgressInline(admin.TabularInline):
    model = LessonProgress
    extra = 0
    readonly_fields = ['student', 'watched_seconds', 'last_position_seconds', 'is_completed', 'completed_at']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'module', 'order', 'lesson_type', 'is_free_preview', 'drip_days', 'created_at']
    list_filter = ['lesson_type', 'is_free_preview', 'course']
    search_fields = ['title', 'course__title']
    inlines = [LessonProgressInline]
    actions = ['enable_free_preview', 'disable_free_preview']

    @admin.action(description="Enable Free Preview for selected lessons")
    def enable_free_preview(self, request, queryset):
        count = queryset.update(is_free_preview=True)
        self.message_user(request, f"Enabled Free Preview for {count} lesson(s).")

    @admin.action(description="Disable Free Preview for selected lessons")
    def disable_free_preview(self, request, queryset):
        count = queryset.update(is_free_preview=False)
        self.message_user(request, f"Disabled Free Preview for {count} lesson(s).")


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'watched_seconds', 'last_position_seconds', 'is_completed', 'completed_at']
    list_filter = ['is_completed', 'completed_at']
    search_fields = ['student__username', 'lesson__title']


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'timestamp_seconds', 'get_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['student__username', 'lesson__title', 'content']

    @admin.display(description='Note Content')
    def get_preview(self, obj):
        return (obj.content[:50] + '...') if len(obj.content) > 50 else obj.content
