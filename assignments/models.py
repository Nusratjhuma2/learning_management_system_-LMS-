from django.conf import settings
from django.db import models
from django.utils import timezone

from courses.models import Course, Module


class Assignment(models.Model):
    """An assignment created by an instructor within a course."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    module = models.ForeignKey(
        Module,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assignments',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    max_score = models.PositiveIntegerField(default=100)
    due_date = models.DateTimeField(null=True, blank=True)
    attachment = models.FileField(upload_to='assignment_files/', blank=True, null=True)
    repo_url_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def is_past_due(self):
        if self.due_date:
            return timezone.now() > self.due_date
        return False

    @property
    def total_submissions(self):
        return self.submissions.count()

    @property
    def pending_grading_count(self):
        return self.submissions.filter(status='submitted').count()


class AssignmentSubmission(models.Model):
    """A student's submission for an assignment."""

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        GRADED = 'graded', 'Graded'

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
    )
    submitted_file = models.FileField(upload_to='submissions/', blank=True, null=True)
    submission_text = models.TextField(blank=True)
    repo_url = models.URLField(blank=True, null=True, help_text='Link to Git repository if requested')
    notes = models.TextField(blank=True, help_text='Additional submission remarks')
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title} ({self.status})"
