import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

from courses.models import Course


class Enrollment(models.Model):
    """Tracks student enrollment, progress metrics, and completion state."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']

    def save(self, *args, **kwargs):
        if self.is_completed:
            self.completed = True
        elif self.completed:
            self.is_completed = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} -> {self.course.title}"

    def get_total_lessons_count(self):
        return self.course.lessons.count()

    def get_completed_lessons_count(self):
        from lessons.models import LessonProgress
        return LessonProgress.objects.filter(
            student=self.student,
            lesson__course=self.course,
            is_completed=True,
        ).count()

    def get_progress_percentage(self):
        return int(float(self.progress_percent))


class Certificate(models.Model):
    """Issued upon successful 100% completion of an enrolled course."""

    enrollment = models.OneToOneField(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='certificate',
    )
    certificate_uid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    certificate_id = models.CharField(max_length=64, unique=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='certificates/', blank=True, null=True)

    class Meta:
        ordering = ['-issued_at']

    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = f"CERT-{self.certificate_uid.hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Certificate {self.certificate_id} for {self.enrollment.student.username}"


class Badge(models.Model):
    """Gamification achievement badge."""

    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, default='🏆', help_text='Icon emoji or class')
    xp_required = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"{self.icon} {self.name} ({self.xp_required} XP)"


class StudentBadge(models.Model):
    """Badge awarded to a student upon earning XP."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_badges',
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'badge']
        ordering = ['-awarded_at']

    def __str__(self):
        return f"{self.student.username} - {self.badge.name}"
