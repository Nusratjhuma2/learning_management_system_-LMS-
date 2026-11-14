import os
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import Course
from .models import Enrollment, Certificate, Badge, StudentBadge
from .services.certificate_service import generate_certificate_pdf, update_enrollment_progress


@login_required
def enroll(request, course_slug):
    """Enroll the current student in a course after checking prerequisites."""
    course = get_object_or_404(Course, slug=course_slug, status=Course.Status.PUBLISHED)

    # Check course prerequisites
    prereqs = course.prerequisite_requirements.select_related('required_course').all()
    unmet_prereqs = []
    for prereq in prereqs:
        req_course = prereq.required_course
        has_completed = Enrollment.objects.filter(
            student=request.user,
            course=req_course,
            is_completed=True,
        ).exists()
        if not has_completed:
            unmet_prereqs.append(req_course.title)

    if unmet_prereqs:
        messages.error(
            request,
            f"Cannot enroll: You must first complete the prerequisite course(s): {', '.join(unmet_prereqs)}.",
        )
        return redirect('courses:course_detail', slug=course.slug)

    # Paid course security check: redirect to checkout if not free
    if not course.is_free and course.effective_price > Decimal('0.00'):
        messages.info(request, f"'{course.title}' is a premium course. Please complete checkout to enroll.")
        return redirect('payments:checkout', course_slug=course.slug)

    enrollment, created = Enrollment.objects.get_or_create(student=request.user, course=course)
    update_enrollment_progress(request.user, course)

    if created:
        messages.success(request, f"Successfully enrolled in '{course.title}'! Welcome aboard.")
    else:
        messages.info(request, f"You are already enrolled in '{course.title}'.")
    return redirect('courses:course_detail', slug=course.slug)


@login_required
def unenroll(request, course_slug):
    """Remove enrollment from a course."""
    course = get_object_or_404(Course, slug=course_slug)
    Enrollment.objects.filter(student=request.user, course=course).delete()
    messages.info(request, f"You have unenrolled from '{course.title}'.")
    return redirect('courses:course_detail', slug=course.slug)


@login_required
def my_courses(request):
    """Show courses the current user is enrolled in with progress indicators."""
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course', 'course__instructor').prefetch_related('course__lessons')

    for enr in enrollments:
        update_enrollment_progress(request.user, enr.course)

    return render(request, 'enrollments/my_courses.html', {
        'enrollments': enrollments,
    })


def verify_certificate(request, certificate_uid):
    """
    Publicly accessible certificate verification endpoint.
    Validates certificate UID against database and displays official accreditation credentials.
    """
    certificate = get_object_or_404(
        Certificate.objects.select_related(
            'enrollment__student',
            'enrollment__course',
            'enrollment__course__instructor',
        ),
        certificate_uid=certificate_uid,
    )

    return render(request, 'enrollments/verify_certificate.html', {
        'certificate': certificate,
        'enrollment': certificate.enrollment,
        'course': certificate.enrollment.course,
        'student': certificate.enrollment.student,
        'instructor': certificate.enrollment.course.instructor,
    })


def download_certificate(request, certificate_uid):
    """Streams the official certificate PDF file to the client."""
    certificate = get_object_or_404(Certificate, certificate_uid=certificate_uid)

    if not certificate.pdf_file or not os.path.exists(certificate.pdf_file.path):
        generate_certificate_pdf(certificate)

    if certificate.pdf_file:
        return FileResponse(
            open(certificate.pdf_file.path, 'rb'),
            content_type='application/pdf',
            as_attachment=True,
            filename=f"Certificate_{certificate.certificate_id}.pdf",
        )
    raise Http404("Certificate document not found.")


@login_required
def my_certificates(request):
    """Student portal view for earned certificates, badges, and gamification stats."""
    certificates = Certificate.objects.filter(
        enrollment__student=request.user,
    ).select_related('enrollment__course', 'enrollment__course__instructor').order_by('-issued_at')

    badges = StudentBadge.objects.filter(
        student=request.user,
    ).select_related('badge').order_by('-awarded_at')

    all_badges = Badge.objects.all()

    return render(request, 'enrollments/my_certificates.html', {
        'certificates': certificates,
        'earned_badges': badges,
        'all_badges': all_badges,
        'xp_points': getattr(request.user, 'xp_points', 0),
        'streak_days': getattr(request.user, 'streak_days', 0),
    })
