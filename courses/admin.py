from decimal import Decimal
from django.contrib import admin

from .models import Announcement, Category, Course, CoursePrerequisite, CourseReview, Module, Wishlist


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'instructor', 'category', 'level', 'price', 'discount_price', 'is_free', 'status', 'created_at']
    list_filter = ['status', 'level', 'is_free', 'category', 'created_at']
    search_fields = ['title', 'description', 'instructor__username']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ModuleInline]
    actions = ['publish_courses', 'archive_courses', 'make_free']

    @admin.action(description="Publish selected courses")
    def publish_courses(self, request, queryset):
        count = queryset.update(status=Course.Status.PUBLISHED)
        self.message_user(request, f"Published {count} course(s).")

    @admin.action(description="Archive selected courses")
    def archive_courses(self, request, queryset):
        count = queryset.update(status=Course.Status.ARCHIVED)
        self.message_user(request, f"Archived {count} course(s).")

    @admin.action(description="Convert selected courses to 100% Free")
    def make_free(self, request, queryset):
        count = queryset.update(is_free=True, price=Decimal('0.00'), discount_price=None)
        self.message_user(request, f"Converted {count} course(s) to Free enrollment.")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order']
    list_filter = ['course']


@admin.register(CoursePrerequisite)
class CoursePrerequisiteAdmin(admin.ModelAdmin):
    list_display = ['course', 'required_course']


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ['course', 'student', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'created_at']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'author', 'is_pinned', 'created_at']
