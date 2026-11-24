import re
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from django.utils import timezone

from courses.models import Course, Module


class PrivateMediaStorage(FileSystemStorage):
    """File storage pointing to the private media root outside public URL paths."""

    def __init__(self, *args, **kwargs):
        kwargs['location'] = getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        return ('lessons.models.PrivateMediaStorage', [], {})


private_storage = PrivateMediaStorage()


class Lesson(models.Model):
    """A lesson belonging to a course and module."""

    class LessonType(models.TextChoices):
        VIDEO = 'video', 'Video'
        ARTICLE = 'article', 'Article'
        PDF = 'pdf', 'PDF'
        LIVE_CLASS = 'live_class', 'Live Class'

    class ContentType(models.TextChoices):
        TEXT = 'text', 'Text'
        VIDEO = 'video', 'Video'
        FILE = 'file', 'File'

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='lessons',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lessons',
    )
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    lesson_type = models.CharField(
        max_length=20,
        choices=LessonType.choices,
        default=LessonType.VIDEO,
    )
    is_free_preview = models.BooleanField(default=False)
    drip_days = models.PositiveIntegerField(default=0)
    min_watch_percent = models.PositiveIntegerField(default=85)
    class TranscodeStatus(models.TextChoices):
        NONE = 'none', 'None'
        PENDING = 'pending', 'Pending'
        READY = 'ready', 'Multi-Quality HLS Ready'
        STREAM_ONLY = 'stream_only', 'Protected Direct Stream'
        FAILED = 'failed', 'Failed'

    raw_video = models.FileField(
        storage=private_storage,
        upload_to='raw_videos/',
        blank=True,
        null=True,
    )
    hls_playlist_relpath = models.CharField(max_length=255, blank=True)
    video_qualities = models.JSONField(default=list, blank=True)
    transcode_status = models.CharField(
        max_length=20,
        choices=TranscodeStatus.choices,
        default=TranscodeStatus.NONE,
    )
    aes_key = models.BinaryField(max_length=16, null=True, blank=True)
    aes_iv = models.CharField(max_length=32, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    transcript_duration_seconds = models.PositiveIntegerField(default=0)

    # Legacy compatibility fields
    content_type = models.CharField(
        max_length=10,
        choices=ContentType.choices,
        default=ContentType.TEXT,
    )
    text_content = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    file_upload = models.FileField(upload_to='lesson_files/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ['course', 'order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def embed_video_url(self):
        """Converts standard YouTube or Vimeo URLs into embeddable URLs."""
        if not self.video_url:
            return ""
        url = self.video_url.strip()
        youtube_regex = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
        match = re.search(youtube_regex, url)
        if match:
            return f"https://www.youtube.com/embed/{match.group(1)}"
        vimeo_regex = r'vimeo\.com\/(?:channels\/(?:\w+\/)?|groups\/([^\/]*)\/videos\/|album\/(\d+)\/video\/|)(\d+)'
        vmatch = re.search(vimeo_regex, url)
        if vmatch:
            return f"https://player.vimeo.com/video/{vmatch.group(3)}"
        return url

    @property
    def is_embed_video(self):
        """Returns True if the video is hosted on YouTube or Vimeo."""
        if not self.video_url:
            return False
        url = self.video_url.lower()
        return bool('youtube.com' in url or 'youtu.be' in url or 'vimeo.com' in url)

    @property
    def has_direct_video(self):
        """Returns True if the lesson has an uploaded raw_video, an HLS stream, or a direct media file URL."""
        if bool(self.raw_video) or bool(self.hls_playlist_relpath):
            return True
        if self.video_url and not self.is_embed_video:
            return True
        return False


class LessonProgress(models.Model):
    """Tracks a student's watch time, position, and completion status for a lesson."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_progresses',
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='progresses',
    )
    watched_seconds = models.PositiveIntegerField(default=0)
    last_position_seconds = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['student', 'lesson']

    def __str__(self):
        status = "Completed" if self.is_completed else "Incomplete"
        return f"{self.student.username} - {self.lesson.title}: {status} ({self.watched_seconds}s)"


class LessonNote(models.Model):
    """Personal private study note taken by a student during a lesson."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_notes',
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    timestamp_seconds = models.PositiveIntegerField(default=0)
    note_text = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['timestamp_seconds', 'created_at']

    def __str__(self):
        return f"Note: {self.student.username} on {self.lesson.title} @ {self.timestamp_seconds}s"

    @property
    def content(self):
        return self.note_text


class LessonTranscriptSegment(models.Model):
    """Timestamped transcript cue line synchronized with video playback."""

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='transcript_segments',
    )
    order = models.PositiveIntegerField(default=1)
    start_seconds = models.FloatField(default=0.0)
    end_seconds = models.FloatField(default=0.0)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_seconds', 'order', 'id']

    def __str__(self):
        return f"{self.lesson.title} [{self.formatted_start}] {self.text[:50]}"

    @property
    def formatted_start(self):
        total = max(int(self.start_seconds), 0)
        mins, secs = divmod(total, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"
