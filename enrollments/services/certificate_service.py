import io
import os
import uuid
import qrcode
from decimal import Decimal
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from accounts.models import User
from assignments.models import Assignment, AssignmentSubmission
from courses.models import Course
from enrollments.models import Enrollment, Certificate, Badge, StudentBadge
from lessons.models import Lesson, LessonProgress
from quizzes.models import Quiz, QuizAttempt


def update_enrollment_progress(student, course):
    """
    Computes overall course completion percentage across lessons, quizzes, and assignments.
    When reaching 100%, awards XP, issues badges, and generates a verifiable QR PDF certificate.
    """
    enrollment, _ = Enrollment.objects.get_or_create(student=student, course=course)

    total_lessons = Lesson.objects.filter(course=course).count()
    total_quizzes = Quiz.objects.filter(course=course).count()
    total_assignments = Assignment.objects.filter(course=course).count()

    total_deliverables = total_lessons + total_quizzes + total_assignments

    if total_deliverables == 0:
        enrollment.progress_percent = Decimal('100.00') if enrollment.is_completed else Decimal('0.00')
        enrollment.save(update_fields=['progress_percent'])
        return enrollment

    completed_lessons = LessonProgress.objects.filter(
        student=student,
        lesson__course=course,
        is_completed=True,
    ).values('lesson').distinct().count()

    passed_quizzes = QuizAttempt.objects.filter(
        student=student,
        quiz__course=course,
        passed=True,
    ).values('quiz').distinct().count()

    graded_assignments = AssignmentSubmission.objects.filter(
        student=student,
        assignment__course=course,
        status=AssignmentSubmission.Status.GRADED,
    ).values('assignment').distinct().count()

    completed_count = completed_lessons + passed_quizzes + graded_assignments
    progress = round(Decimal((completed_count / total_deliverables) * 100), 2)
    progress = min(Decimal('100.00'), progress)

    enrollment.progress_percent = progress

    if progress >= Decimal('100.00') and not enrollment.is_completed:
        enrollment.is_completed = True
        enrollment.completed = True
        enrollment.completed_at = timezone.now()

        # Gamification: Award 100 XP
        if hasattr(student, 'xp_points'):
            student.xp_points = (student.xp_points or 0) + 100
            student.save(update_fields=['xp_points'])

        # Check and unlock eligible badges
        eligible_badges = Badge.objects.filter(xp_required__lte=student.xp_points)
        for badge in eligible_badges:
            StudentBadge.objects.get_or_create(student=student, badge=badge)

        enrollment.save()

        # Generate Certificate
        cert, _ = Certificate.objects.get_or_create(enrollment=enrollment)
        generate_certificate_pdf(cert)
        return enrollment

    enrollment.save(update_fields=['progress_percent'])
    return enrollment


def generate_certificate_pdf(certificate):
    """
    Renders an official, executive landscape PDF certificate with verification QR code.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    student_name = certificate.enrollment.student.get_full_name() or certificate.enrollment.student.username
    course_title = certificate.enrollment.course.title
    instructor_name = certificate.enrollment.course.instructor.get_full_name() or certificate.enrollment.course.instructor.username
    issue_date = (certificate.issued_at or timezone.now()).strftime("%B %d, %Y")
    cert_id = certificate.certificate_id or f"CERT-{certificate.certificate_uid.hex[:10].upper()}"

    # Generate QR Code for verification
    verification_url = f"/enrollments/verify/{certificate.certificate_uid}/"
    qr_img = qrcode.make(verification_url)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)

    # Styles
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'CertHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        textTransform='uppercase',
        spaceAfter=15,
    )

    title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=30,
        leading=36,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=15,
    )

    subtitle_style = ParagraphStyle(
        'CertSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#475569'),
        alignment=1,
        spaceAfter=15,
    )

    name_style = ParagraphStyle(
        'CertName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=colors.HexColor('#0F172A'),
        alignment=1,
        spaceAfter=15,
    )

    course_style = ParagraphStyle(
        'CertCourse',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        alignment=1,
        spaceAfter=25,
    )

    footer_style = ParagraphStyle(
        'CertFooter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748B'),
    )

    elements = [
        Spacer(1, 15),
        Paragraph("Executive Accreditation & Professional Certification", header_style),
        Paragraph("CERTIFICATE OF COMPLETION", title_style),
        Spacer(1, 5),
        Paragraph("This certifies that the candidate named below has fulfilled all requisite academic milestones:", subtitle_style),
        Spacer(1, 10),
        Paragraph(student_name, name_style),
        Spacer(1, 5),
        Paragraph(f"has successfully completed the comprehensive curriculum of", subtitle_style),
        Paragraph(course_title, course_style),
        Spacer(1, 15),
    ]

    # Footer Table with Instructor Signature line, Certificate ID, and QR Code
    qr_image_flowable = Image(qr_buffer, width=70, height=70)

    footer_data = [
        [
            Paragraph(f"<b>Instructor:</b> {instructor_name}<br/><font color='#94A3B8'>Authorized Course Evaluator</font>", footer_style),
            Paragraph(f"<b>Issued Date:</b> {issue_date}<br/><b>Accreditation UID:</b> {cert_id}", footer_style),
            qr_image_flowable,
        ]
    ]

    footer_table = Table(footer_data, colWidths=[280, 300, 100])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('LINEABOVE', (0, 0), (1, 0), 1, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))

    elements.append(footer_table)

    # Frame drawing callback for border
    def draw_borders(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#0F172A'))
        canvas.setLineWidth(3)
        canvas.rect(20, 20, landscape(letter)[0] - 40, landscape(letter)[1] - 40)
        canvas.setStrokeColor(colors.HexColor('#94A3B8'))
        canvas.setLineWidth(1)
        canvas.rect(24, 24, landscape(letter)[0] - 48, landscape(letter)[1] - 48)
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_borders)
    buffer.seek(0)

    file_name = f"certificate_{certificate.certificate_uid}.pdf"
    certificate.pdf_file.save(file_name, ContentFile(buffer.getvalue()), save=True)
    return certificate

