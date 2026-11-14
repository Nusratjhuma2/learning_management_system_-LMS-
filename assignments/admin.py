from django.contrib import admin
from .models import Assignment, AssignmentSubmission


class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    extra = 0
    readonly_fields = ['submitted_at', 'graded_at']


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'max_score', 'due_date', 'total_submissions']
    list_filter = ['course', 'due_date']
    search_fields = ['title', 'course__title']
    inlines = [AssignmentSubmissionInline]


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'student', 'status', 'score', 'submitted_at', 'graded_at']
    list_filter = ['status', 'assignment__course']
    search_fields = ['student__username', 'assignment__title']
