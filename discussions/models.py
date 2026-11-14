from django.conf import settings
from django.db import models

from courses.models import Course
from lessons.models import Lesson


class DiscussionThread(models.Model):
    """A discussion forum or Q&A thread belonging to a course (and optionally a specific lesson)."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='discussion_threads',
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discussion_threads',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='threads_started',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    upvotes = models.PositiveIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"[{self.course.title}] {self.title}"

    @property
    def replies_count(self):
        return self.replies.count()

    @property
    def body(self):
        return self.content

    @body.setter
    def body(self, value):
        self.content = value


class DiscussionReply(models.Model):
    """A reply to a discussion thread."""

    thread = models.ForeignKey(
        DiscussionThread,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='thread_replies',
    )
    content = models.TextField()
    is_instructor_reply = models.BooleanField(default=False)
    is_instructor_solution = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on '{self.thread.title}'"

    @property
    def body(self):
        return self.content

    @body.setter
    def body(self, value):
        self.content = value


class CourseAnnouncement(models.Model):
    """Broadcast announcement from an instructor to all students in a course."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='course_announcements',
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_announcements',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Announcement: {self.title} ({self.course.title})"


class Notification(models.Model):
    """User in-app notifications for replies, announcements, and certifications."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=200)
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.title}"
