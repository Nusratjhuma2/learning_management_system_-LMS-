from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permissions import (
    deny_role_redirect,
    is_admin_user,
    is_course_manager,
    is_instructor_user,
    is_student_user,
)
from courses.models import Course
from .forms import AssignmentForm, AssignmentSubmissionForm, GradingForm
from .models import Assignment, AssignmentSubmission


@login_required
def assignment_detail(request, pk):
    """View assignment details and submission status."""
    assignment = get_object_or_404(
        Assignment.objects.select_related('course', 'course__instructor'),
        pk=pk,
    )
    course = assignment.course
    is_instructor = is_course_manager(request.user, course)
    is_enrolled = is_student_user(request.user) and course.enrollments.filter(student=request.user).exists()

    if not is_instructor and not is_enrolled:
        messages.error(request, "You must be enrolled in this course to view this assignment.")
        return redirect('courses:course_detail', slug=course.slug)

    submission = None
    submission_form = None
    if is_enrolled:
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=request.user,
        ).first()
        submission_form = AssignmentSubmissionForm(instance=submission)

    return render(request, 'assignments/assignment_detail.html', {
        'assignment': assignment,
        'course': course,
        'is_instructor': is_instructor,
        'is_enrolled': is_enrolled,
        'submission': submission,
        'submission_form': submission_form,
    })


@login_required
def submit_assignment(request, pk):
    """Handle student assignment file upload or text submission."""
    assignment = get_object_or_404(Assignment, pk=pk)
    course = assignment.course

    if not is_student_user(request.user):
        return deny_role_redirect(
            request,
            "Only enrolled students can submit assignments.",
            'assignments:assignment_detail',
            pk=assignment.pk,
        )

    if not course.enrollments.filter(student=request.user).exists():
        messages.error(request, "You are not enrolled in this course.")
        return redirect('courses:course_detail', slug=course.slug)

    submission, created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        student=request.user,
    )

    if request.method == 'POST':
        form = AssignmentSubmissionForm(request.POST, request.FILES, instance=submission)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.status = AssignmentSubmission.Status.SUBMITTED
            sub.submitted_at = timezone.now()
            sub.save()
            messages.success(request, "Your assignment was submitted successfully!")
            return redirect('assignments:assignment_detail', pk=assignment.pk)
    return redirect('assignments:assignment_detail', pk=assignment.pk)


@login_required
def assignment_create(request, course_slug):
    """Instructor or admin creates a new assignment for a course."""
    course = get_object_or_404(Course, slug=course_slug)
    if not is_course_manager(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            assignment.save()
            messages.success(request, f"Assignment '{assignment.title}' created.")
            return redirect('courses:course_detail', slug=course.slug)
    else:
        form = AssignmentForm()

    return render(request, 'assignments/assignment_form.html', {
        'form': form,
        'course': course,
        'title': 'Create Assignment',
    })


@login_required
def assignment_update(request, pk):
    """Instructor or admin edits an assignment."""
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=pk)
    if not is_course_manager(request.user, assignment.course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=assignment.course.slug)

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, "Assignment updated successfully.")
            return redirect('assignments:assignment_detail', pk=assignment.pk)
    else:
        form = AssignmentForm(instance=assignment)

    return render(request, 'assignments/assignment_form.html', {
        'form': form,
        'course': assignment.course,
        'title': 'Edit Assignment',
    })


@login_required
def assignment_delete(request, pk):
    """Instructor or admin deletes an assignment."""
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=pk)
    course = assignment.course
    if not is_course_manager(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        assignment.delete()
        messages.success(request, "Assignment deleted.")
        return redirect('courses:course_detail', slug=course.slug)

    return render(request, 'assignments/assignment_confirm_delete.html', {'assignment': assignment})


@login_required
def submissions_list(request, pk):
    """Instructor or admin reviews all submissions for an assignment."""
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=pk)
    if not is_course_manager(request.user, assignment.course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=assignment.course.slug)

    filter_status = request.GET.get('status', 'all')
    submissions = assignment.submissions.select_related('student')
    if filter_status == 'submitted':
        submissions = submissions.filter(status='submitted')
    elif filter_status == 'graded':
        submissions = submissions.filter(status='graded')

    return render(request, 'assignments/submissions_list.html', {
        'assignment': assignment,
        'submissions': submissions,
        'filter_status': filter_status,
    })


@login_required
def grade_submission(request, submission_id):
    """Instructor or admin grades an individual student submission."""
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related('assignment', 'assignment__course', 'student'),
        pk=submission_id,
    )
    course = submission.assignment.course
    if not is_course_manager(request.user, course):
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        form = GradingForm(request.POST, instance=submission)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.status = AssignmentSubmission.Status.GRADED
            sub.graded_at = timezone.now()
            sub.save()
            messages.success(request, f"Graded submission for {submission.student.username} successfully.")
            return redirect('assignments:submissions_list', pk=submission.assignment.pk)
    else:
        form = GradingForm(instance=submission)

    return render(request, 'assignments/grade_submission.html', {
        'submission': submission,
        'form': form,
    })


@login_required
def instructor_assignments_list(request):
    """Instructor or admin overview of published assignments."""
    if not (is_instructor_user(request.user) or is_admin_user(request.user)):
        return deny_role_redirect(request, "Permission denied.")

    if is_admin_user(request.user):
        assignments = Assignment.objects.all().select_related('course').prefetch_related('submissions')
    else:
        assignments = Assignment.objects.filter(
            course__instructor=request.user
        ).select_related('course').prefetch_related('submissions')
    return render(request, 'assignments/instructor_assignments.html', {
        'assignments': assignments,
    })
