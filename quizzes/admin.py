from django.contrib import admin

from .models import Choice, Question, Quiz, QuizAttempt, QuizAttemptAnswer


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1


class QuizAttemptAnswerInline(admin.TabularInline):
    model = QuizAttemptAnswer
    extra = 0
    readonly_fields = ['question', 'selected_choice', 'text_answer', 'is_correct']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'passing_score', 'time_limit_minutes', 'max_attempts', 'enforce_anticheat', 'created_at']
    list_filter = ['course', 'enforce_anticheat']
    search_fields = ['title', 'course__title']
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text', 'quiz', 'question_type', 'points', 'order']
    list_filter = ['quiz__course', 'question_type']
    search_fields = ['text', 'quiz__title']
    inlines = [ChoiceInline]


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ['text', 'question', 'is_correct']
    list_filter = ['is_correct', 'question__quiz']
    search_fields = ['text', 'question__text']


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'quiz', 'score', 'passed', 'is_disqualified', 'tab_switch_count', 'completed_at']
    list_filter = ['passed', 'is_disqualified', 'completed_at']
    search_fields = ['student__username', 'quiz__title']
    inlines = [QuizAttemptAnswerInline]
    actions = ['clear_disqualification']

    @admin.action(description="Clear disqualification for selected attempts")
    def clear_disqualification(self, request, queryset):
        count = queryset.update(is_disqualified=False, tab_switch_count=0)
        self.message_user(request, f"Cleared disqualifications for {count} quiz attempt(s).")


@admin.register(QuizAttemptAnswer)
class QuizAttemptAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question', 'selected_choice', 'is_correct']
    list_filter = ['is_correct']
    search_fields = ['attempt__student__username', 'question__text']
