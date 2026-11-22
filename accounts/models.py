from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with role, device limits, gamification, and security support."""

    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        INSTRUCTOR = 'instructor', 'Instructor'
        ADMIN = 'admin', 'Admin'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    bio = models.TextField(blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
    )
    phone_number = models.CharField(max_length=30, blank=True, verbose_name="Phone Number")
    
    # Address Information
    address = models.CharField(max_length=255, blank=True, verbose_name="Street Address")
    city = models.CharField(max_length=100, blank=True, verbose_name="City")
    state = models.CharField(max_length=100, blank=True, verbose_name="State / Province")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Postal / ZIP Code")
    country = models.CharField(max_length=100, blank=True, verbose_name="Country")

    # Academic Information
    institution_name = models.CharField(max_length=200, blank=True, verbose_name="Institution / University", help_text="Current school, college, or university")
    student_id = models.CharField(max_length=50, blank=True, verbose_name="Student / Academic ID", help_text="Institutional registration or student ID number")
    department = models.CharField(max_length=150, blank=True, verbose_name="Department / Faculty", help_text="e.g. Department of Computer Science")
    degree_program = models.CharField(max_length=150, blank=True, verbose_name="Degree / Major Program", help_text="e.g. B.Sc. in Computer Science & Engineering")
    academic_year = models.CharField(max_length=50, blank=True, verbose_name="Academic Year / Level", help_text="e.g. 1st Year, Senior, Graduate")
    gpa = models.CharField(max_length=20, blank=True, verbose_name="GPA / Grade Point Average", help_text="e.g. 3.85 / 4.00")

    max_devices = models.PositiveIntegerField(default=2)
    xp_points = models.PositiveIntegerField(default=0)
    streak_days = models.PositiveIntegerField(default=0)

    @property
    def full_address(self):
        parts = [p for p in [self.address, self.city, self.state, self.postal_code, self.country] if p]
        return ", ".join(parts) if parts else ""

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_instructor(self):
        return self.role == self.Role.INSTRUCTOR

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
            self.is_staff = True
        elif self.role == self.Role.ADMIN:
            self.is_staff = True
        else:
            self.is_staff = False
        super().save(*args, **kwargs)


class Administrator(User):
    """Proxy model for dedicated Administrator management and permission governance."""

    class Meta:
        proxy = True
        verbose_name = 'Administrator'
        verbose_name_plural = 'Administrators'

    def save(self, *args, **kwargs):
        self.role = self.Role.ADMIN
        self.is_staff = True
        self.is_superuser = True
        super().save(*args, **kwargs)


class ActiveUserSession(models.Model):
    """Tracks the single active session per user to enforce single-login policy."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='active_session',
    )
    session_key = models.CharField(max_length=40, db_index=True)
    device_fingerprint = models.CharField(max_length=128, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.session_key}"


class TrustedDevice(models.Model):
    """Tracks trusted devices for a user up to user.max_devices."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trusted_devices',
    )
    device_fingerprint = models.CharField(max_length=128)
    device_name = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    last_used_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'device_fingerprint']
        ordering = ['-last_used_at']

    def __str__(self):
        return f"{self.user.username} - {self.device_name or self.device_fingerprint[:12]}"


class SecurityAuditLog(models.Model):
    """Audit logs for security events across the LMS platform."""

    class EventType(models.TextChoices):
        CONCURRENT_LOGIN_KICKED = 'CONCURRENT_LOGIN_KICKED', 'Concurrent Login Kicked'
        WATERMARK_TAMPER = 'WATERMARK_TAMPER', 'Watermark Tamper'
        SCREEN_CAPTURE_ATTEMPT = 'SCREEN_CAPTURE_ATTEMPT', 'Screen Capture Attempt'
        DEVTOOLS_OPENED = 'DEVTOOLS_OPENED', 'DevTools Opened'
        UNAUTHORIZED_STREAM = 'UNAUTHORIZED_STREAM', 'Unauthorized Stream'

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_logs',
    )
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        user_repr = self.user.username if self.user else "Anonymous"
        return f"[{self.event_type}] {user_repr} @ {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
