from django.conf import settings
from django.db import models
from django.utils import timezone

from courses.models import Course, Module


class Quiz(models.Model):
    """A timed, anti-cheat enabled assessment associated with a course and optional module."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='quizzes')
    module = models.ForeignKey(Module, null=True, blank=True, on_delete=models.SET_NULL, related_name='quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(
        default=15,
        help_text='Time limit in minutes (0 for no limit)',
    )
    time_limit_mins = models.PositiveIntegerField(
        default=15,
        help_text='Time limit in minutes (0 for no limit)',
    )
    max_attempts = models.PositiveIntegerField(
        default=3,
        help_text='Maximum allowed attempts (0 for unlimited)',
    )
    pass_mark_percent = models.PositiveIntegerField(
        default=70,
        help_text='Minimum percentage to pass',
    )
    passing_score = models.PositiveIntegerField(
        default=70,
        help_text='Minimum percentage to pass',
    )
    shuffle_questions = models.BooleanField(default=True)
    shuffle_choices = models.BooleanField(default=True)
    enforce_anticheat = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'quizzes'
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        if self.time_limit_minutes:
            self.time_limit_mins = self.time_limit_minutes
        elif self.time_limit_mins:
            self.time_limit_minutes = self.time_limit_mins
        if self.pass_mark_percent:
            self.passing_score = self.pass_mark_percent
        elif self.passing_score:
            self.pass_mark_percent = self.passing_score
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def total_questions(self):
        return self.questions.count()


class Question(models.Model):
    """A question in a quiz with type variants."""

    QUESTION_TYPES = [
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
        default='single_choice',
    )
    points = models.PositiveIntegerField(default=1)
    short_answer_solution = models.CharField(
        max_length=255,
        blank=True,
        help_text='Correct answer for short-answer questions (evaluated case-insensitively)',
    )
    order = models.PositiveIntegerField(default=0)
    explanation = models.TextField(
        blank=True,
        help_text='Explanation revealed after student submits attempt',
    )

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"[{self.get_question_type_display()}] {self.text[:80]}"


class Choice(models.Model):
    """An answer choice for a question."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    """A student's attempt at a quiz, including anti-cheat violation metrics."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    score = models.FloatField(default=0)
    passed = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(default=timezone.now)
    tab_switch_count = models.PositiveIntegerField(default=0)
    is_disqualified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        status = 'Disqualified' if self.is_disqualified else f"{self.score}%"
        return f"{self.student.username} - {self.quiz.title}: {status}"


class QuizAttemptAnswer(models.Model):
    """Stores the specific choices or text answer submitted by student."""

    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    selected_choices = models.ManyToManyField(
        Choice,
        blank=True,
        related_name='attempt_answers',
    )
    text_answer = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    points_awarded = models.FloatField(default=0.0)

    def __str__(self):
        return f"Attempt {self.attempt_id} - Q{self.question_id}: {'Correct' if self.is_correct else 'Wrong'}"
