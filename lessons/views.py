import json
import mimetypes
import os
import re
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Max
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import SecurityAuditLog
from accounts.signals import get_client_ip
from courses.models import Course
from courses.services.curriculum import build_course_curriculum_state, is_lesson_accessible_by_module
from enrollments.models import Enrollment

from .forms import LessonForm
from .models import Lesson, LessonNote, LessonProgress
from .services.hls_transcoder import (
    ALLOWED_QUALITIES,
    get_cdn_media_url,
    get_private_media_root,
    transcode_lesson_video,
)
from .services.transcript_generator import generate_lesson_transcript


def get_hls_signer():
    return TimestampSigner(salt='hls')


def check_lesson_access(user, lesson):
    """Verify if a user has permission to access the lesson. Only enrolled students, the instructor, or superuser can access."""
    if not user.is_authenticated:
        return False
    if user == lesson.course.instructor or user.is_superuser:
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

    # Check sequential module completion and drip content locking
    allowed, lock_reason = is_lesson_accessible_by_module(lesson, request.user)
    if not allowed:
        messages.warning(request, lock_reason or "This lesson is currently locked.")
        return redirect('courses:course_detail', slug=course_slug)

    # Get or create student's lesson progress
    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)

    # Automatically trigger HLS / metadata processing if raw_video uploaded and not yet processed
    if lesson.raw_video and lesson.transcode_status == Lesson.TranscodeStatus.NONE and not lesson.hls_playlist_relpath:
        transcode_lesson_video(lesson)

    # Auto-generate timestamped transcript cues if lesson has text_content and no cues yet
    transcript_segments = list(lesson.transcript_segments.all())
    if not transcript_segments and lesson.text_content.strip():
        transcript_segments = generate_lesson_transcript(lesson)

    # Generate signed token for HLS & protected stream playback
    signer = get_hls_signer()
    stream_token = signer.sign(f"{request.user.id}:{lesson.id}")

    protected_stream_url = ''
    if lesson.raw_video:
        protected_stream_url = (
            reverse('lessons:protected_stream', kwargs={'course_slug': course_slug, 'lesson_id': lesson.id})
            + f"?token={stream_token}"
        )

    transcript_cues = [
        {
            'id': seg.id,
            'order': seg.order,
            'start': float(seg.start_seconds),
            'end': float(seg.end_seconds),
            'formatted_start': seg.formatted_start,
            'text': seg.text,
        }
        for seg in transcript_segments
    ]

    is_instructor_or_admin = (
        request.user == lesson.course.instructor
        or request.user.is_superuser
        or request.user.is_staff
        or getattr(request.user, 'is_admin', False)
    )

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
            'protected_stream_url': protected_stream_url,
            'transcript_segments': transcript_segments,
            'transcript_cues_json': json.dumps(transcript_cues),
            'video_qualities': lesson.video_qualities or [],
            'is_instructor_or_admin': is_instructor_or_admin,
            'client_ip': get_client_ip(request) or '127.0.0.1',
            'completed_count': completed_lessons,
            'total_lessons': total_course_lessons,
        },
    )


def _verify_stream_request(request, lesson, max_age=3600):
    """Validate course enrollment, module unlock state, and signed token."""
    if not check_lesson_access(request.user, lesson):
        return False, HttpResponseForbidden("Unauthorized streaming request.")

    allowed, lock_reason = is_lesson_accessible_by_module(lesson, request.user)
    if not allowed:
        return False, HttpResponseForbidden(lock_reason or "Module locked.")

    token = request.GET.get('token')
    if not token:
        return False, HttpResponseForbidden("Missing stream token.")

    signer = get_hls_signer()
    try:
        data = signer.unsign(token, max_age=max_age)
        user_id, l_id = data.split(':')
        if int(user_id) != request.user.id or int(l_id) != lesson.id:
            return False, HttpResponseForbidden("Invalid stream token payload.")
    except (BadSignature, SignatureExpired, ValueError):
        return False, HttpResponseForbidden("Stream token expired or invalid.")

    return True, None


def _rewrite_hls_playlist_lines(lines, course_slug, lesson, fresh_token, quality=None):
    """Rewrite master or variant m3u8 playlist references to signed protected URLs."""
    output_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#EXT-X-KEY:'):
            key_url = reverse('lessons:hls_key', kwargs={'course_slug': course_slug, 'lesson_id': lesson.id})
            output_lines.append(f'#EXT-X-KEY:METHOD=AES-128,URI="{key_url}?token={fresh_token}",IV=0x{lesson.aes_iv}\n')
        elif stripped.endswith('index.m3u8') and '/' in stripped:
            variant_quality = stripped.split('/')[0]
            if variant_quality in ALLOWED_QUALITIES:
                variant_url = reverse(
                    'lessons:hls_variant_manifest',
                    kwargs={'course_slug': course_slug, 'lesson_id': lesson.id, 'quality': variant_quality},
                )
                output_lines.append(f"{variant_url}?token={fresh_token}\n")
            else:
                output_lines.append(line)
        elif stripped.endswith('.ts'):
            rel_seg = f"hls/{lesson.id}/{quality}/{stripped}" if quality else f"hls/{lesson.id}/{stripped}"
            cdn_url = get_cdn_media_url(rel_seg)
            if cdn_url:
                output_lines.append(f"{cdn_url}?token={fresh_token}\n")
            elif quality:
                seg_url = reverse(
                    'lessons:hls_variant_segment',
                    kwargs={'course_slug': course_slug, 'lesson_id': lesson.id, 'quality': quality, 'segment_name': stripped},
                )
                output_lines.append(f"{seg_url}?token={fresh_token}\n")
            else:
                seg_url = reverse(
                    'lessons:hls_segment',
                    kwargs={'course_slug': course_slug, 'lesson_id': lesson.id, 'segment_name': stripped},
                )
                output_lines.append(f"{seg_url}?token={fresh_token}\n")
        else:
            output_lines.append(line)
    return ''.join(output_lines)


@login_required
def lesson_hls_manifest(request, course_slug, lesson_id):
    """Serves the secure HLS master or root .m3u8 manifest with signed resource URLs."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    if not lesson.hls_playlist_relpath:
        raise Http404("HLS stream not available.")

    private_root = Path(get_private_media_root())
    manifest_path = private_root / lesson.hls_playlist_relpath
    if not manifest_path.exists():
        raise Http404("Manifest file missing on disk.")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fresh_token = get_hls_signer().sign(f"{request.user.id}:{lesson.id}")
    body = _rewrite_hls_playlist_lines(lines, course_slug, lesson, fresh_token)

    resp = HttpResponse(body, content_type='application/vnd.apple.mpegurl')
    resp['Cache-Control'] = 'private, no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp


@login_required
def lesson_hls_variant_manifest(request, course_slug, lesson_id, quality):
    """Serves a specific quality tier HLS playlist (1080p, 720p, or 480p)."""
    if quality not in ALLOWED_QUALITIES:
        raise Http404("Unsupported stream quality.")

    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    private_root = Path(get_private_media_root())
    manifest_path = private_root / 'hls' / str(lesson.id) / quality / 'index.m3u8'
    if not manifest_path.exists():
        raise Http404("Variant playlist not found.")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fresh_token = get_hls_signer().sign(f"{request.user.id}:{lesson.id}")
    body = _rewrite_hls_playlist_lines(lines, course_slug, lesson, fresh_token, quality=quality)

    resp = HttpResponse(body, content_type='application/vnd.apple.mpegurl')
    resp['Cache-Control'] = 'private, no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp


@login_required
def lesson_hls_key(request, course_slug, lesson_id):
    """Serves the 16-byte AES-128 decryption key over signed channel."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    if not lesson.aes_key:
        return HttpResponseForbidden("Decryption key not found.")

    resp = HttpResponse(lesson.aes_key, content_type='application/octet-stream')
    resp['Cache-Control'] = 'private, no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp


def _serve_ts_segment(request, lesson, seg_path):
    if not seg_path.exists():
        raise Http404("Segment file not found.")
    with open(seg_path, 'rb') as f:
        data = f.read()
    resp = HttpResponse(data, content_type='video/MP2T')
    resp['Cache-Control'] = 'private, max-age=300'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


@login_required
def lesson_hls_segment(request, course_slug, lesson_id, segment_name):
    """Streams encrypted video chunks from protected private storage."""
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    safe_segment_name = os.path.basename(segment_name)
    seg_path = Path(get_private_media_root()) / 'hls' / str(lesson.id) / safe_segment_name
    return _serve_ts_segment(request, lesson, seg_path)


@login_required
def lesson_hls_variant_segment(request, course_slug, lesson_id, quality, segment_name):
    """Streams encrypted quality-specific HLS segments (1080p/720p/480p)."""
    if quality not in ALLOWED_QUALITIES:
        raise Http404("Unsupported stream quality.")
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    safe_segment_name = os.path.basename(segment_name)
    seg_path = Path(get_private_media_root()) / 'hls' / str(lesson.id) / quality / safe_segment_name
    return _serve_ts_segment(request, lesson, seg_path)


def _file_range_iterator(path, offset, length, chunk_size=65536):
    remaining = length
    with open(path, 'rb') as fh:
        fh.seek(offset)
        while remaining > 0:
            read_len = min(chunk_size, remaining)
            data = fh.read(read_len)
            if not data:
                break
            remaining -= len(data)
            yield data


@login_required
def lesson_protected_stream(request, course_slug, lesson_id):
    """
    Token-signed protected HTTP Range stream for directly uploaded private videos
    when FFmpeg HLS segments are not yet generated. Blocks unauthenticated/unenrolled
    access and supports HTTP 206 byte-range seeking cleanly.
    """
    lesson = get_object_or_404(Lesson, pk=lesson_id, course__slug=course_slug)
    ok, err_resp = _verify_stream_request(request, lesson, max_age=3600)
    if not ok:
        return err_resp

    if not lesson.raw_video:
        raise Http404("No direct video available.")

    file_path = Path(lesson.raw_video.path)
    if not file_path.exists():
        raise Http404("Video file missing on disk.")

    file_size = file_path.stat().st_size
    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or 'video/mp4'

    range_header = request.META.get('HTTP_RANGE', '').strip()
    range_match = re.match(r'^bytes=(\d*)-(\d*)$', range_header)

    if range_match:
        first_byte = int(range_match.group(1)) if range_match.group(1) else 0
        last_byte = int(range_match.group(2)) if range_match.group(2) else (file_size - 1)
        last_byte = min(last_byte, file_size - 1)
        if first_byte >= file_size or last_byte < first_byte:
            resp = HttpResponse(status=416)
            resp['Content-Range'] = f'bytes */{file_size}'
            return resp
        length = last_byte - first_byte + 1
        resp = StreamingHttpResponse(
            _file_range_iterator(file_path, first_byte, length),
            status=206,
            content_type=content_type,
        )
        resp['Content-Range'] = f'bytes {first_byte}-{last_byte}/{file_size}'
        resp['Content-Length'] = str(length)
    else:
        resp = FileResponse(open(file_path, 'rb'), content_type=content_type)
        resp['Content-Length'] = str(file_size)

    resp['Accept-Ranges'] = 'bytes'
    resp['Content-Disposition'] = 'inline'
    resp['Cache-Control'] = 'private, no-store, no-cache, must-revalidate'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


def _build_lesson_progress_payload(user, lesson):
    """Build updated course/module progress payload after lesson progress changes."""
    curriculum = build_course_curriculum_state(lesson.course, user)
    payload = {
        'overall_progress_percent': curriculum['overall_progress_percent'],
        'completed_items': curriculum['completed_items'],
        'total_items': curriculum['total_items'],
        'module_id': lesson.module_id,
        'module_completed': False,
        'module_completed_count': 0,
        'module_total_count': 0,
        'module_progress_percent': 0,
        'unlocked_next_module': None,
    }
    if lesson.module_id:
        sections = curriculum['sections']
        for idx, sec in enumerate(sections):
            if sec['id'] == lesson.module_id:
                payload['module_completed'] = sec['is_completed']
                payload['module_completed_count'] = sec['completed_count']
                payload['module_total_count'] = sec['total_count']
                payload['module_progress_percent'] = sec['progress_percent']
                if sec['is_completed']:
                    for nxt in sections[idx + 1:]:
                        if not nxt['is_standalone'] and nxt['is_unlocked']:
                            payload['unlocked_next_module'] = {
                                'id': nxt['id'],
                                'title': nxt['title'],
                            }
                            break
                break
    return payload


@login_required
@require_POST
def lesson_heartbeat_api(request, lesson_id):
    """
    Heartbeat called every 10s of active playback.
    Increments watched_seconds safely and completes lesson when >= min_watch_percent.
    """
    lesson = get_object_or_404(Lesson.objects.select_related('course', 'module'), pk=lesson_id)
    if not check_lesson_access(request.user, lesson):
        return JsonResponse({'status': 'forbidden', 'message': 'Enrollment required.'}, status=403)

    allowed, lock_reason = is_lesson_accessible_by_module(lesson, request.user)
    if not allowed:
        return JsonResponse({'status': 'locked', 'message': lock_reason}, status=403)

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

    effective_duration = lesson.transcript_duration_seconds or lesson.duration_seconds
    threshold_seconds = (effective_duration * lesson.min_watch_percent) / 100.0 if effective_duration > 0 else 30
    if progress.watched_seconds >= threshold_seconds and not progress.is_completed:
        progress.is_completed = True
        progress.completed_at = timezone.now()

    progress.save()

    try:
        from enrollments.services.certificate_service import update_enrollment_progress
        update_enrollment_progress(request.user, lesson.course)
    except Exception:
        pass

    response_data = {
        'status': 'ok',
        'watched_seconds': progress.watched_seconds,
        'is_completed': progress.is_completed,
    }
    response_data.update(_build_lesson_progress_payload(request.user, lesson))
    return JsonResponse(response_data)


@login_required
@require_POST
def mark_lesson_completed_api(request, lesson_id):
    """Explicitly marks a lesson as completed (for embedded YouTube videos, readings, or PDFs)."""
    lesson = get_object_or_404(Lesson.objects.select_related('course', 'module'), pk=lesson_id)
    if not check_lesson_access(request.user, lesson):
        return JsonResponse({'status': 'forbidden', 'message': 'Enrollment required.'}, status=403)

    allowed, lock_reason = is_lesson_accessible_by_module(lesson, request.user)
    if not allowed:
        return JsonResponse({'status': 'locked', 'message': lock_reason}, status=403)

    progress, _ = LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    progress.is_completed = True
    progress.completed_at = timezone.now()
    progress.save()

    try:
        from enrollments.services.certificate_service import update_enrollment_progress
        update_enrollment_progress(request.user, lesson.course)
    except Exception:
        pass

    response_data = {'status': 'ok', 'is_completed': True}
    response_data.update(_build_lesson_progress_payload(request.user, lesson))
    return JsonResponse(response_data)


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
@require_POST
def generate_transcript_api(request, lesson_id):
    """
    Generate or update timestamped transcript cues for a lesson and sync
    transcript duration length with the custom web player.
    """
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    is_privileged = (
        request.user == lesson.course.instructor
        or request.user.is_superuser
        or request.user.is_staff
        or getattr(request.user, 'is_admin', False)
    )
    if not is_privileged:
        return JsonResponse({'status': 'forbidden', 'message': 'Permission denied.'}, status=403)

    try:
        data = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload.'}, status=400)

    raw_text = data.get('raw_text')
    create_default = bool(data.get('create_default', False))
    raw_target = data.get('target_duration_seconds')
    target_duration = None
    if raw_target not in (None, ''):
        try:
            target_duration = max(int(float(raw_target)), 1)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid target duration.'}, status=400)

    segments = generate_lesson_transcript(
        lesson,
        raw_text=raw_text,
        target_duration_seconds=target_duration,
        create_default=create_default,
    )
    if not segments:
        return JsonResponse(
            {'status': 'empty', 'message': 'Provide transcript text or enable auto-outline generation.'},
            status=400,
        )

    return JsonResponse({
        'status': 'ok',
        'transcript_duration_seconds': lesson.transcript_duration_seconds,
        'duration_seconds': lesson.duration_seconds,
        'cues': [
            {
                'id': seg.id,
                'order': seg.order,
                'start': float(seg.start_seconds),
                'end': float(seg.end_seconds),
                'formatted_start': seg.formatted_start,
                'text': seg.text,
            }
            for seg in segments
        ],
    })


@login_required
def lesson_create(request, course_slug):
    """Add a lesson to a course (course author or platform administrator)."""
    is_admin = request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'
    if is_admin:
        course = get_object_or_404(Course, slug=course_slug)
    else:
        course = get_object_or_404(Course, slug=course_slug, instructor=request.user)

    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES)
        form.fields['module'].queryset = course.modules.order_by('order', 'id')
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.course = course
            lesson.save()
            if lesson.raw_video:
                transcode_lesson_video(lesson)
            if lesson.text_content.strip() or lesson.raw_video:
                generate_lesson_transcript(lesson, create_default=False)
            return redirect('courses:course_detail', slug=course.slug)
    else:
        next_order = (course.lessons.aggregate(max_order=Max('order'))['max_order'] or 0) + 1
        form = LessonForm(initial={'order': next_order})
        form.fields['module'].queryset = course.modules.order_by('order', 'id')
    return render(request, 'lessons/lesson_form.html', {
        'form': form,
        'course': course,
        'title': 'Add Lesson',
    })


@login_required
def lesson_update(request, course_slug, pk):
    """Edit a lesson (course author or platform administrator)."""
    is_admin = request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'
    if is_admin:
        lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug)
    else:
        lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug, course__instructor=request.user)

    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        form.fields['module'].queryset = lesson.course.modules.order_by('order', 'id')
        if form.is_valid():
            lesson = form.save()
            if 'raw_video' in request.FILES or (lesson.raw_video and lesson.transcode_status == Lesson.TranscodeStatus.NONE):
                transcode_lesson_video(lesson)
            if lesson.text_content.strip():
                generate_lesson_transcript(lesson, create_default=False)
            return redirect('lessons:lesson_detail', course_slug=course_slug, pk=lesson.pk)
    else:
        form = LessonForm(instance=lesson)
        form.fields['module'].queryset = lesson.course.modules.order_by('order', 'id')
    return render(request, 'lessons/lesson_form.html', {
        'form': form,
        'course': lesson.course,
        'title': 'Edit Lesson',
    })


@login_required
def lesson_delete(request, course_slug, pk):
    """Delete a lesson (course author or platform administrator)."""
    is_admin = request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'
    if is_admin:
        lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug)
    else:
        lesson = get_object_or_404(Lesson, pk=pk, course__slug=course_slug, course__instructor=request.user)

    course = lesson.course
    if request.method == 'POST':
        lesson.delete()
        return redirect('courses:course_detail', slug=course.slug)
    return render(request, 'lessons/lesson_confirm_delete.html', {'lesson': lesson})
