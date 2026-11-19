from django.contrib import admin
from django.utils import timezone

from .models import Badge, Certificate, Enrollment, StudentBadge
from .services.certificate_service import generate_certificate_pdf


class CertificateInline(admin.StackedInline):
    model = Certificate
    extra = 0
    readonly_fields = ['certificate_id', 'certificate_uid', 'issued_at']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'progress_percent', 'is_completed', 'enrolled_at', 'completed_at']
    list_filter = ['is_completed', 'enrolled_at']
    search_fields = ['student__username', 'student__email', 'course__title']
    inlines = [CertificateInline]
    actions = ['mark_completed_and_issue_cert', 'reset_student_progress']

    @admin.action(description="Mark fully completed & auto-issue certificate")
    def mark_completed_and_issue_cert(self, request, queryset):
        issued = 0
        for enrollment in queryset:
            enrollment.is_completed = True
            enrollment.completed = True
            enrollment.progress_percent = 100.00
            enrollment.completed_at = timezone.now()
            enrollment.save()

            cert, _ = Certificate.objects.get_or_create(enrollment=enrollment)
            generate_certificate_pdf(cert)
            issued += 1
        self.message_user(request, f"Marked {issued} enrollment(s) completed and generated academic certificates.")

    @admin.action(description="Reset progress back to zero")
    def reset_student_progress(self, request, queryset):
        count = queryset.update(
            progress_percent=0.00,
            is_completed=False,
            completed=False,
            completed_at=None,
        )
        self.message_user(request, f"Reset progress for {count} enrollment(s).")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_id', 'get_student', 'get_course', 'issued_at', 'has_pdf']
    list_filter = ['issued_at']
    search_fields = ['certificate_id', 'enrollment__student__username', 'enrollment__course__title']
    readonly_fields = ['certificate_uid', 'certificate_id', 'issued_at']
    actions = ['regenerate_pdf_certificates']

    @admin.display(description='Student')
    def get_student(self, obj):
        return obj.enrollment.student.username

    @admin.display(description='Course')
    def get_course(self, obj):
        return obj.enrollment.course.title

    @admin.display(description='PDF Available', boolean=True)
    def has_pdf(self, obj):
        return bool(obj.pdf_file)

    @admin.action(description="Regenerate PDF file for selected certificates")
    def regenerate_pdf_certificates(self, request, queryset):
        count = 0
        for cert in queryset:
            generate_certificate_pdf(cert)
            count += 1
        self.message_user(request, f"Regenerated PDF for {count} certificate(s).")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'xp_required', 'description']
    search_fields = ['name']


@admin.register(StudentBadge)
class StudentBadgeAdmin(admin.ModelAdmin):
    list_display = ['student', 'badge', 'awarded_at']
    list_filter = ['badge', 'awarded_at']
    search_fields = ['student__username', 'badge__name']
