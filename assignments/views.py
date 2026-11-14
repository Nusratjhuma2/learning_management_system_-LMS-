from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

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
    is_instructor = request.user == course.instructor or request.user.is_admin
    is_enrolled = course.enrollments.filter(student=request.user).exists()

    if not is_instructor and not is_enrolled:
        messages.error(request, "You must be enrolled in this course to view this assignment.")
        return redirect('courses:course_detail', slug=course.slug)

    submission = None
    submission_form = None
    if not is_instructor:
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
    """Instructor creates a new assignment for a course."""
    course = get_object_or_404(Course, slug=course_slug)
    if request.user != course.instructor and not request.user.is_admin:
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
    """Instructor edits an assignment."""
    assignment = get_object_or_404(Assignment, pk=pk)
    if request.user != assignment.course.instructor and not request.user.is_admin:
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
    """Instructor deletes an assignment."""
    assignment = get_object_or_404(Assignment, pk=pk)
    course = assignment.course
    if request.user != course.instructor and not request.user.is_admin:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        assignment.delete()
        messages.success(request, "Assignment deleted.")
        return redirect('courses:course_detail', slug=course.slug)

    return render(request, 'assignments/assignment_confirm_delete.html', {'assignment': assignment})


@login_required
def submissions_list(request, pk):
    """Instructor reviews all submissions for an assignment."""
    assignment = get_object_or_404(Assignment, pk=pk)
    if request.user != assignment.course.instructor and not request.user.is_admin:
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
    """Instructor grades an individual student submission."""
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related('assignment', 'assignment__course', 'student'),
        pk=submission_id,
    )
    course = submission.assignment.course
    if request.user != course.instructor and not request.user.is_admin:
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
    """Instructor overview of all assignments they have published."""
    if not request.user.is_instructor and not request.user.is_admin:
        return redirect('dashboard:index')

    assignments = Assignment.objects.filter(
        course__instructor=request.user
    ).select_related('course').prefetch_related('submissions')
    return render(request, 'assignments/instructor_assignments.html', {
        'assignments': assignments,
    })
