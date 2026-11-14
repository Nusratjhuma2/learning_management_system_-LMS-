import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.models import Course
from enrollments.models import Enrollment
from lessons.models import Lesson
from .forms import ReplyForm, ThreadForm
from .models import CourseAnnouncement, DiscussionReply, DiscussionThread, Notification


@login_required
def course_discussions(request, course_slug):
    """List discussion threads for a specific course."""
    course = get_object_or_404(Course, slug=course_slug)
    is_enrolled = course.enrollments.filter(student=request.user).exists()
    is_instructor = request.user == course.instructor or getattr(request.user, 'is_admin', False) or request.user.is_staff

    if not is_enrolled and not is_instructor and course.status != Course.Status.PUBLISHED:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_list')

    filter_type = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '').strip()

    threads = course.discussion_threads.select_related('author', 'lesson').prefetch_related('replies')

    if search_query:
        threads = threads.filter(title__icontains=search_query) | threads.filter(content__icontains=search_query)

    if filter_type == 'unresolved':
        threads = threads.filter(is_resolved=False)
    elif filter_type == 'resolved':
        threads = threads.filter(is_resolved=True)
    elif filter_type == 'mine':
        threads = threads.filter(author=request.user)

    announcements = course.course_announcements.select_related('instructor').all()[:5]

    return render(request, 'discussions/course_discussions.html', {
        'course': course,
        'threads': threads,
        'announcements': announcements,
        'filter_type': filter_type,
        'search_query': search_query,
        'is_enrolled': is_enrolled,
        'is_instructor': is_instructor,
    })


@login_required
def thread_create(request, course_slug):
    """Start a new discussion thread."""
    course = get_object_or_404(Course, slug=course_slug)
    is_enrolled = course.enrollments.filter(student=request.user).exists()
    is_instructor = request.user == course.instructor or getattr(request.user, 'is_admin', False) or request.user.is_staff

    if not is_enrolled and not is_instructor:
        messages.error(request, "You must be enrolled to participate in discussions.")
        return redirect('courses:course_detail', slug=course.slug)

    lesson_id = request.GET.get('lesson')
    initial_data = {}
    if lesson_id:
        initial_data['lesson'] = lesson_id

    if request.method == 'POST':
        form = ThreadForm(course, request.POST)
        if form.is_valid():
            thread = form.save(commit=False)
            thread.course = course
            thread.author = request.user
            thread.save()

            # Notify instructor if student posted
            if request.user != course.instructor:
                Notification.objects.create(
                    recipient=course.instructor,
                    title=f"New discussion on '{course.title}': {thread.title}",
                    link=f"/discussions/thread/{thread.pk}/",
                )

            messages.success(request, "Discussion thread posted.")
            return redirect('discussions:thread_detail', pk=thread.pk)
    else:
        form = ThreadForm(course, initial=initial_data)

    return render(request, 'discussions/thread_form.html', {
        'form': form,
        'course': course,
    })


@login_required
def thread_detail(request, pk):
    """View a discussion thread and its replies."""
    thread = get_object_or_404(
        DiscussionThread.objects.select_related('course', 'author', 'lesson'),
        pk=pk,
    )
    course = thread.course
    is_enrolled = course.enrollments.filter(student=request.user).exists()
    is_instructor = request.user == course.instructor or getattr(request.user, 'is_admin', False) or request.user.is_staff

    replies = thread.replies.select_related('author').all()
    reply_form = ReplyForm()

    return render(request, 'discussions/thread_detail.html', {
        'thread': thread,
        'course': course,
        'replies': replies,
        'reply_form': reply_form,
        'is_instructor': is_instructor,
        'is_enrolled': is_enrolled,
    })


@login_required
def reply_create(request, pk):
    """Post a reply to a thread."""
    thread = get_object_or_404(DiscussionThread.objects.select_related('course'), pk=pk)
    course = thread.course
    is_instructor = request.user == course.instructor or getattr(request.user, 'is_admin', False) or request.user.is_staff
    is_enrolled = course.enrollments.filter(student=request.user).exists()

    if not is_instructor and not is_enrolled:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        form = ReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.thread = thread
            reply.author = request.user
            reply.is_instructor_reply = (request.user == course.instructor or request.user.is_staff)
            reply.save()

            # Notify author if someone else replied
            if thread.author != request.user:
                Notification.objects.create(
                    recipient=thread.author,
                    title=f"New reply on your thread: '{thread.title}'",
                    link=f"/discussions/thread/{thread.pk}/",
                )

            messages.success(request, "Reply posted successfully.")

    return redirect('discussions:thread_detail', pk=thread.pk)


@login_required
def toggle_resolve(request, pk):
    """Mark a thread as resolved or unresolved."""
    thread = get_object_or_404(DiscussionThread, pk=pk)
    if request.user == thread.author or request.user == thread.course.instructor or request.user.is_staff:
        thread.is_resolved = not thread.is_resolved
        thread.save(update_fields=['is_resolved'])
        status_str = "resolved" if thread.is_resolved else "open"
        messages.success(request, f"Thread marked as {status_str}.")
    return redirect('discussions:thread_detail', pk=thread.pk)


@login_required
@require_POST
def create_thread_api(request, lesson_id):
    """AJAX endpoint to create a Q&A thread inside a lesson detail view."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    try:
        data = json.loads(request.body.decode('utf-8'))
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()

        if not title or not body:
            return JsonResponse({'status': 'error', 'message': 'Title and question body are required.'}, status=400)

        thread = DiscussionThread.objects.create(
            course=lesson.course,
            lesson=lesson,
            author=request.user,
            title=title,
            content=body,
        )

        # Notify instructor
        if request.user != lesson.course.instructor:
            Notification.objects.create(
                recipient=lesson.course.instructor,
                title=f"Lesson Q&A from {request.user.username}: {title}",
                link=f"/discussions/thread/{thread.pk}/",
            )

        return JsonResponse({
            'status': 'ok',
            'thread_id': thread.pk,
            'title': thread.title,
            'author': thread.author.get_full_name() or thread.author.username,
            'created_at': thread.created_at.strftime("%b %d, %Y"),
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def reply_thread_api(request, thread_id):
    """AJAX endpoint to reply to a thread."""
    thread = get_object_or_404(DiscussionThread.objects.select_related('course'), pk=thread_id)
    try:
        data = json.loads(request.body.decode('utf-8'))
        body = data.get('body', '').strip()
        is_solution = bool(data.get('is_instructor_solution', False))

        if not body:
            return JsonResponse({'status': 'error', 'message': 'Reply content cannot be empty.'}, status=400)

        is_instructor = request.user == thread.course.instructor or request.user.is_staff
        reply = DiscussionReply.objects.create(
            thread=thread,
            author=request.user,
            content=body,
            is_instructor_reply=is_instructor,
            is_instructor_solution=is_solution and is_instructor,
        )

        if reply.is_instructor_solution:
            thread.is_resolved = True
            thread.save(update_fields=['is_resolved'])

        if thread.author != request.user:
            Notification.objects.create(
                recipient=thread.author,
                title=f"Answer posted on '{thread.title}'",
                link=f"/discussions/thread/{thread.pk}/",
            )

        return JsonResponse({
            'status': 'ok',
            'reply_id': reply.pk,
            'author': reply.author.get_full_name() or reply.author.username,
            'content': reply.content,
            'created_at': reply.created_at.strftime("%b %d, %Y"),
            'is_instructor': reply.is_instructor_reply,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def create_announcement(request, course_slug):
    """Instructor broadcasts an announcement to all course students."""
    course = get_object_or_404(Course, slug=course_slug)
    if request.user != course.instructor and not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect('courses:course_detail', slug=course.slug)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()

        if title and content:
            announcement = CourseAnnouncement.objects.create(
                course=course,
                instructor=request.user,
                title=title,
                content=content,
            )

            # Broadcast notification to enrolled students
            enrollments = course.enrollments.select_related('student').all()
            notifications = [
                Notification(
                    recipient=enr.student,
                    title=f"Course Announcement: {title} ({course.title})",
                    link=f"/courses/{course.slug}/",
                )
                for enr in enrollments if enr.student != request.user
            ]
            Notification.objects.bulk_create(notifications)

            messages.success(request, f"Announcement broadcasted to {len(notifications)} enrolled students.")
            return redirect('courses:course_detail', slug=course.slug)
        else:
            messages.error(request, "Title and content cannot be blank.")

    return render(request, 'discussions/announcement_form.html', {
        'course': course,
    })


@login_required
def notifications_list(request):
    """View and clear student/instructor notifications."""
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')

    if request.GET.get('action') == 'mark_read':
        notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        return redirect('discussions:notifications_list')

    return render(request, 'discussions/notifications_list.html', {
        'notifications': notifications,
    })
