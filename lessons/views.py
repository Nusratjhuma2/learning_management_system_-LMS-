import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import SecurityAuditLog
from accounts.signals import get_client_ip
from courses.models import Course
from enrollments.models import Enrollment

from .forms import LessonForm
from .models import Lesson, LessonNote, LessonProgress
from .services.hls_transcoder import get_private_media_root, transcode_lesson_video


def get_hls_signer():
    return TimestampSigner(salt='hls')


def check_lesson_access(user, lesson):
    """Verify if a user has permission to access the lesson."""
    if not user.is_authenticated:
        return False
    if lesson.is_free_preview:
        return True
    if user == lesson.course.instructor or user.is_staff or getattr(user, 'is_admin', False):
        return True
    return Enrollment.objects.filter(student=user, course=lesson.course).exists()


@login_required
def lesson_detail(request, course_slug, pk):
    """View a single lesson with anti-download player and interactive notes."""
    lesson = get_object_or_404(
        Lesson.objects.select_related('course', 'course__instructor', 'module'),
        pk=pk,
        course__slug=course_slug,
    )

    if not check_lesson_access(request.user, lesson):
        messages.error(request, "You must be enrolled in this course to access this lesson.")
        return redirect('courses:course_detail', slug=course_slug)

    # Check drip content scheduling
    if lesson.drip_days > 0 and not (request.user == lesson.course.instructor or request.user.is_staff):
        enrollment = Enrollment.objects.filter(student=request.user, course=lesson.course).first()
        if enrollment:
            days_enrolled = (timezone.now() - enrollment.enrolled_at).days
            if days_enrolled < lesson.drip_days:
                unlock_in = lesson.drip_days - days_enrolled
                messages.warning(
                    request,
                    f"This lesson is locked. It will unlock in {unlock_in} day{'s' if unlock_in > 1 else ''} as part of scheduled course release.",
                )
                return redirect('courses:course_detail', slug=course_slug)

    # Check sequential lesson completion locking
    if not (request.user == lesson.course.instructor or request.user.is_staff or getattr(request.user, 'is_admin', False)):
        uncompleted_prev = (
            lesson.course.lessons.filter(order__lt=lesson.order)
            .exclude(progresses__student=request.user, progresses__is_completed=True)
            .first()
        )
        if uncompleted_prev:
            messages.warning(
                request,
                f"Sequential learning locked: You must complete prior lecture '{uncompleted_prev.title}' before continuing.",
            )
            return redirect('courses:course_detail', slug=course_slug)

    # Get or create student's lesson progress
    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)

    # Automatically trigger HLS transcoding if raw_video is uploaded and not yet transcoded
    if lesson.raw_video and not lesson.hls_playlist_relpath:
        transcode_lesson_video(lesson)

    # Generate short-lived signed token for HLS streaming (valid for 120 seconds)
    signer = get_hls_signer()
    stream_token = signer.sign(f"{request.user.id}:{lesson.id}")

    notes = lesson.notes.filter(student=request.user)
    all_lessons = lesson.course.lessons.select_related('module').order_by('order', 'id')

    # Calculate completion percent for student in this course
    total_course_lessons = all_lessons.count()
    completed_lessons = LessonProgress.objects.filter(
        student=request.user,
        lesson__course=lesson.course,
        is_completed=True,
    ).count()

    return render(
        request,
        'lessons/lesson_detail.html',
        {
            'lesson': lesson,
            'progress': progress,
            'notes': notes,
            'all_lessons': all_lessons,
            'stream_token': stream_token,
            'client_ip': get_client_ip(request) or '127.0.0.1',
            'completed_count': completed_lessons,
            'total_lessons': total_course_lessons,
        },
    )


@login_required
def lesson_hls_manifest(request, course_slug, lesson_id):
    """Serves the secure HLS .m3u8 manifest with signed resource URLs."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    if not check_lesson_access(request.user, lesson):
        return HttpResponseForbidden("Unauthorized streaming request.")

    token = request.GET.get('token')
    if not token:
        return HttpResponseForbidden("Missing stream token.")

    signer = get_hls_signer()
    try:
        data = signer.unsign(token, max_age=120)
        user_id, l_id = data.split(':')
        if int(user_id) != request.user.id or int(l_id) != lesson.id:
            return HttpResponseForbidden("Invalid stream token payload.")
    except (BadSignature, SignatureExpired, ValueError):
        return HttpResponseForbidden("Stream token expired or invalid.")

    if not lesson.hls_playlist_relpath:
        raise Http404("HLS stream not available.")

    private_root = Path(get_private_media_root())
    manifest_path = private_root / lesson.hls_playlist_relpath
    if not manifest_path.exists():
        raise Http404("Manifest file missing on disk.")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Rewrite segment and key references to secure signed endpoints
    fresh_token = signer.sign(f"{request.user.id}:{lesson.id}")
    output_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#EXT-X-KEY:'):
            # Replace key URI with secured endpoint
            key_url = reverse('lessons:hls_key', kwargs={'course_slug': course_slug, 'lesson_id': lesson.id})
            output_lines.append(f'#EXT-X-KEY:METHOD=AES-128,URI="{key_url}?token={fresh_token}",IV=0x{lesson.aes_iv}\n')
        elif stripped.endswith('.ts'):
            seg_url = reverse(
                'lessons:hls_segment',
                kwargs={'course_slug': course_slug, 'lesson_id': lesson.id, 'segment_name': stripped},
            )
            output_lines.append(f"{seg_url}?token={fresh_token}\n")
        else:
            output_lines.append(line)

    resp = HttpResponse(''.join(output_lines), content_type='application/vnd.apple.mpegurl')
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp


@login_required
def lesson_hls_key(request, course_slug, lesson_id):
    """Serves the 16-byte AES-128 decryption key over secure channel."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    if not check_lesson_access(request.user, lesson):
        return HttpResponseForbidden("Unauthorized key request.")

    token = request.GET.get('token')
    if not token:
        return HttpResponseForbidden("Missing security token.")

    signer = get_hls_signer()
    try:
        signer.unsign(token, max_age=120)
    except (BadSignature, SignatureExpired):
        return HttpResponseForbidden("Security token expired.")

    if not lesson.aes_key:
        return HttpResponseForbidden("Decryption key not found.")

    resp = HttpResponse(lesson.aes_key, content_type='application/octet-stream')
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp


@login_required
def lesson_hls_segment(request, course_slug, lesson_id, segment_name):
    """Streams encrypted video chunks from protected private storage."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    if not check_lesson_access(request.user, lesson):
        return HttpResponseForbidden("Access denied.")

    token = request.GET.get('token')
    if not token:
        return HttpResponseForbidden("Missing stream token.")

    signer = get_hls_signer()
    try:
        signer.unsign(token, max_age=180)
    except (BadSignature, SignatureExpired):
        return HttpResponseForbidden("Stream segment token expired.")

    private_root = Path(get_private_media_root())
    # Protect against path traversal
    safe_segment_name = os.path.basename(segment_name)
    seg_path = private_root / 'hls' / str(lesson.id) / safe_segment_name
    if not seg_path.exists():
        raise Http404("Segment file not found.")

    with open(seg_path, 'rb') as f:
        data = f.read()

    resp = HttpResponse(data, content_type='video/MP2T')
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp


@login_required
@require_POST
def lesson_heartbeat_api(request, lesson_id):
    """
    Heartbeat called every 10s of active playback.
    Increments watched_seconds safely and completes lesson when >= min_watch_percent.
    """
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    try:
        data = json.loads(request.body)
        position = float(data.get('current_position', 0))
        delta = float(data.get('delta_watched', 0))
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid payload'}, status=400)

    # Speed-spoofing cap: pulse cannot exceed 15s in a 10s heartbeat
    safe_delta = min(max(delta, 0), 15.0)

    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    progress.watched_seconds += int(safe_delta)
    progress.last_position_seconds = max(int(position), 0)

    threshold_seconds = (lesson.duration_seconds * lesson.min_watch_percent) / 100.0 if lesson.duration_seconds > 0 else 30
    if progress.watched_seconds >= threshold_seconds and not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = timezone.now()

        # Update enrollment overall progress
        try:
            from enrollments.services.certificate_service import update_enrollment_progress
            update_enrollment_progress(request.user, lesson.course)
        except Exception:
            pass

    progress.save()

    return JsonResponse({
        'status': 'ok',
        'watched_seconds': progress.watched_seconds,
        'is_completed': progress.is_completed,
    })


@login_required
@require_POST
def mark_lesson_completed_api(request, lesson_id):
    """Explicitly marks a lesson as completed (for embedded YouTube videos, readings, or PDFs)."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    progress.is_completed = True
    progress.completed_at = timezone.now()
    progress.save()

    try:
        from enrollments.services.certificate_service import update_enrollment_progress
        update_enrollment_progress(request.user, lesson.course)
    except Exception:
        pass

    return JsonResponse({'status': 'ok', 'is_completed': True})


@login_required
@require_POST
def log_security_violation_api(request):
    """Logs client-side security alerts (watermark tamper, devtools, capture attempt)."""
    try:
        data = json.loads(request.body)
        event_type = data.get('event_type', 'WATERMARK_TAMPER')
        details = data.get('details', {})
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error'}, status=400)

    valid_events = [e.value for e in SecurityAuditLog.EventType]
    if event_type not in valid_events:
        event_type = SecurityAuditLog.EventType.WATERMARK_TAMPER

    SecurityAuditLog.objects.create(
        user=request.user,
        event_type=event_type,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
        details=details,
    )
    return JsonResponse({'status': 'recorded'})


@login_required
@require_POST
def lesson_save_note_api(request, lesson_id):
    """Save a private study note timestamped to the lesson video."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    try:
        data = json.loads(request.body)
        timestamp = int(data.get('timestamp_seconds', 0))
        note_text = str(data.get('note_text', '')).strip()
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error'}, status=400)

    if not note_text:
        return JsonResponse({'status': 'empty'}, status=400)

    note = LessonNote.objects.create(
        student=request.user,
        lesson=lesson,
        timestamp_seconds=timestamp,
        note_text=note_text,
    )

    return JsonResponse({
        'status': 'ok',
        'id': note.id,
        'timestamp': note.timestamp_seconds,
        'text': note.note_text,
        'created_at': note.created_at.strftime('%Y-%m-%d %H:%M'),
    })


@login_required
def lesson_create(request, course_slug):
    """Add a lesson to a course (course owner only)."""
    course = get_object_or_404(Course, slug=course_slug, instructor=request.user)
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.course = course
            lesson.save()
            if lesson.raw_video:
                transcode_lesson_video(lesson)
            return redirect('courses:course_detail', slug=course.slug)
    else:
        form = LessonForm()
    return render(request, 'lessons/lesson_form.html', {
        'form': form,
        'course': course,
        'title': 'Add Lesson',
    })


@login_required
def lesson_update(request, course_slug, pk):
    """Edit a lesson (course owner only)."""
    lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug, course__instructor=request.user)
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            lesson = form.save()
            if lesson.raw_video and not lesson.hls_playlist_relpath:
                transcode_lesson_video(lesson)
            return redirect('lessons:lesson_detail', course_slug=course_slug, pk=lesson.pk)
    else:
        form = LessonForm(instance=lesson)
    return render(request, 'lessons/lesson_form.html', {
        'form': form,
        'course': lesson.course,
        'title': 'Edit Lesson',
    })


@login_required
def lesson_delete(request, course_slug, pk):
    """Delete a lesson (course owner only)."""
    lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug, course__instructor=request.user)
    course = lesson.course
    if request.method == 'POST':
        lesson.delete()
        return redirect('courses:course_detail', slug=course.slug)
    return render(request, 'lessons/lesson_confirm_delete.html', {'lesson': lesson})
