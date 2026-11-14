from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """Course category for organization."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Course(models.Model):
    """A course created by an instructor."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED = 'advanced', 'Advanced'

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses_created',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses',
    )
    level = models.CharField(
        max_length=20,
        choices=Level.choices,
        default=Level.BEGINNER,
    )
    language = models.CharField(max_length=50, default='English')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_free = models.BooleanField(default=False)
    preview_video_url = models.URLField(blank=True)
    requirements = models.TextField(
        blank=True,
        help_text='Prerequisites or requirements for this course',
    )
    what_you_will_learn = models.TextField(
        blank=True,
        help_text='Key learning outcomes (one per line or summary)',
    )
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def total_lessons(self):
        return self.lessons.count()

    @property
    def total_students(self):
        return self.enrollments.count()

    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if not reviews.exists():
            return 0.0
        return round(sum(r.rating for r in reviews) / reviews.count(), 1)

    @property
    def reviews_count(self):
        return self.reviews.count()

    @property
    def has_discount(self):
        """Check if course has an active promotional discount."""
        if self.is_free or self.discount_price is None or not self.price:
            return False
        return Decimal('0.00') < self.discount_price < self.price

    @property
    def effective_price(self):
        """Final price after applying discount (or zero if free). Always Decimal."""
        if self.is_free:
            return Decimal('0.00')
        if self.has_discount:
            return self.discount_price
        return self.price or Decimal('0.00')

    @property
    def discount_percentage(self):
        """Calculate discount percentage rounded to the nearest integer."""
        if self.has_discount and self.price and self.price > Decimal('0.00'):
            pct = ((self.price - self.discount_price) / self.price) * Decimal('100')
            return int(round(pct))
        return 0

    @property
    def savings_amount(self):
        """Calculate total dollar savings between regular and discount price."""
        if self.has_discount and self.price and self.discount_price:
            return round(self.price - self.discount_price, 2)
        return Decimal('0.00')

    @property
    def formatted_price(self):
        """Formatted string representation of price or 'Free'."""
        eff = self.effective_price
        if self.is_free or eff <= Decimal('0.00'):
            return "Free"
        return f"${eff:.2f}"

    def clean(self):
        super().clean()
        if self.is_free:
            self.price = Decimal('0.00')
            self.discount_price = None
        else:
            if self.discount_price is not None and self.price is not None:
                if self.discount_price >= self.price:
                    raise ValidationError({'discount_price': 'Discount price must be strictly less than the standard course price.'})

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = slugify(self.title)

        if self.is_free:
            self.price = Decimal('0.00')
            self.discount_price = None
        else:
            if self.price is None or self.price <= Decimal('0.00'):
                if not self.discount_price or self.discount_price <= Decimal('0.00'):
                    self.is_free = True
                    self.price = Decimal('0.00')
                    self.discount_price = None

            if self.discount_price is not None and self.price is not None:
                if self.discount_price <= Decimal('0.00') or self.discount_price >= self.price:
                    self.discount_price = None

        super().save(*args, **kwargs)


class Module(models.Model):
    """Course curriculum module/section containing lessons and quizzes."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='modules',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ['course', 'order']

    def __str__(self):
        return f"{self.course.title} - Module {self.order}: {self.title}"


class CoursePrerequisite(models.Model):
    """Defines a course required before enrolling in another course."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='prerequisite_requirements',
    )
    required_course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='required_for_courses',
    )

    class Meta:
        unique_together = ['course', 'required_course']

    def __str__(self):
        return f"{self.course.title} requires {self.required_course.title}"


class Wishlist(models.Model):
    """Student wishlist for courses."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='wishlisted_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} wishlisted {self.course.title}"


class Announcement(models.Model):
    """Course or site-wide announcements."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='announcements',
        help_text='Leave empty for global platform announcements',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='announcements_authored',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        prefix = f"[{self.course.title}] " if self.course else "[Global] "
        return f"{prefix}{self.title}"


class CourseReview(models.Model):
    """Student feedback and rating for a course."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_reviews',
    )
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['course', 'student']

    def __str__(self):
        return f"{self.student.username} - {self.course.title} ({self.rating}★)"
