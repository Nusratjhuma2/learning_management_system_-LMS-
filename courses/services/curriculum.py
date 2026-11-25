from django.core.signing import TimestampSigner
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from accounts.permissions import is_course_manager, is_student_user
from enrollments.models import Enrollment
from lessons.models import LessonProgress
from quizzes.models import QuizAttempt


def _format_duration(seconds):
    """Format seconds into mm:ss or hh:mm:ss string."""
    if not seconds or seconds <= 0:
        return ''
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _user_bypasses_locks(course, user):
    """Course author and platform administrators bypass student progression locks."""
    return is_course_manager(user, course)


def _get_module_completion_counts(module, completed_lesson_ids, passed_quiz_ids):
    """Return (completed_count, total_count, is_completed) for a single Module."""
    lessons = list(module.lessons.all())
    quizzes = list(module.quizzes.all())
    total_items = len(lessons) + len(quizzes)
    completed_items = (
        sum(1 for lesson in lessons if lesson.id in completed_lesson_ids)
        + sum(1 for quiz in quizzes if quiz.id in passed_quiz_ids)
    )
    is_completed = True if total_items == 0 else (completed_items >= total_items)
    return completed_items, total_items, is_completed


def get_module_unlock_status(module, user):
    """
    Determine whether `module` is unlocked for `user`.
    Module N unlocks only once every earlier Module (< order/id) in the same course
    has all its lessons completed and quizzes passed.
    """
    if module is None:
        return True, ""

    course = module.course
    if _user_bypasses_locks(course, user):
        return True, ""

    if not user or not user.is_authenticated:
        return False, "Sign in and enroll to access course modules."

    if not Enrollment.objects.filter(student=user, course=course).exists():
        return False, "Enroll in this course to unlock modules."

    ordered_modules = list(
        course.modules.prefetch_related('lessons', 'quizzes').order_by('order', 'id')
    )
    completed_lesson_ids = set(
        LessonProgress.objects.filter(
            student=user, lesson__course=course, is_completed=True
        ).values_list('lesson_id', flat=True)
    )
    passed_quiz_ids = set(
        QuizAttempt.objects.filter(
            student=user, quiz__course=course, passed=True
        ).values_list('quiz_id', flat=True)
    )

    for prev_mod in ordered_modules:
        if prev_mod.id == module.id:
            break
        done_count, total_count, is_done = _get_module_completion_counts(
            prev_mod, completed_lesson_ids, passed_quiz_ids
        )
        if not is_done:
            return (
                False,
                f"Complete module '{prev_mod.title}' ({done_count}/{total_count} completed) to unlock '{module.title}'.",
            )

    return True, ""


def is_lesson_accessible_by_module(lesson, user):
    """Check sequential module lock (plus drip lock) for a lesson."""
    if _user_bypasses_locks(lesson.course, user):
        return True, ""

    unlocked, reason = get_module_unlock_status(lesson.module, user)
    if not unlocked:
        return False, reason

    if lesson.drip_days > 0 and user and user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=user, course=lesson.course).first()
        if enrollment:
            days_enrolled = (timezone.now() - enrollment.enrolled_at).days
            if days_enrolled < lesson.drip_days:
                unlock_in = lesson.drip_days - days_enrolled
                return (
                    False,
                    f"This lesson unlocks in {unlock_in} day{'s' if unlock_in > 1 else ''}.",
                )

    return True, ""


def is_quiz_accessible_by_module(quiz, user):
    """Check sequential module lock for a quiz."""
    return get_module_unlock_status(quiz.module, user)


def build_course_curriculum_state(course, user):
    """
    Build structured module/lecture/quiz hierarchy, completion progress,
    sequential module unlock states, and short-window playback metadata.
    """
    modules = list(
        course.modules.prefetch_related('lessons', 'quizzes').order_by('order', 'id')
    )
    standalone_lessons = list(
        course.lessons.filter(module__isnull=True).order_by('order', 'id')
    )
    standalone_quizzes = list(
        course.quizzes.filter(module__isnull=True).order_by('created_at', 'id')
    )

    is_authenticated = bool(user and user.is_authenticated)
    is_privileged = _user_bypasses_locks(course, user)
    is_student = is_student_user(user)
    enrollment = (
        Enrollment.objects.filter(student=user, course=course).first()
        if is_student else None
    )
    is_enrolled = bool(enrollment)
    has_course_access = is_enrolled or is_privileged

    completed_lesson_ids = set()
    progress_map = {}
    passed_quiz_ids = set()
    best_quiz_scores = {}

    if is_authenticated:
        for lp in LessonProgress.objects.filter(student=user, lesson__course=course):
            progress_map[lp.lesson_id] = lp
            if lp.is_completed:
                completed_lesson_ids.add(lp.lesson_id)

        attempts = (
            QuizAttempt.objects.filter(student=user, quiz__course=course)
            .values('quiz_id')
            .annotate(best_score=Max('score'))
        )
        for row in attempts:
            best_quiz_scores[row['quiz_id']] = round(float(row['best_score'] or 0), 1)
        passed_quiz_ids = set(
            QuizAttempt.objects.filter(
                student=user, quiz__course=course, passed=True
            ).values_list('quiz_id', flat=True)
        )

    signer = TimestampSigner(salt='hls') if has_course_access else None

    def _serialize_lesson(lesson, section_unlocked):
        lp = progress_map.get(lesson.id)
        is_completed = lesson.id in completed_lesson_ids
        watched_seconds = lp.watched_seconds if lp else 0
        last_position_seconds = lp.last_position_seconds if lp else 0

        drip_locked = False
        drip_unlock_days = 0
        if lesson.drip_days > 0 and enrollment and not is_privileged:
            days_enrolled = (timezone.now() - enrollment.enrolled_at).days
            if days_enrolled < lesson.drip_days:
                drip_locked = True
                drip_unlock_days = lesson.drip_days - days_enrolled

        lesson_unlocked = has_course_access and section_unlocked and not drip_locked
        can_preview = (not has_course_access) and lesson.is_free_preview
        can_open = lesson_unlocked or can_preview

        has_video = bool(lesson.is_embed_video or lesson.has_direct_video)
        video_kind = ''
        video_src = ''
        if has_video and lesson_unlocked:
            if lesson.is_embed_video:
                video_kind = 'embed'
                video_src = lesson.embed_video_url
            elif lesson.hls_playlist_relpath and signer and is_authenticated:
                video_kind = 'hls'
                token = signer.sign(f"{user.id}:{lesson.id}")
                base_url = reverse('lessons:hls_manifest', args=[course.slug, lesson.id])
                video_src = f"{base_url}?token={token}"
            elif lesson.raw_video and signer and is_authenticated:
                video_kind = 'direct'
                token = signer.sign(f"{user.id}:{lesson.id}")
                base_url = reverse('lessons:protected_stream', args=[course.slug, lesson.id])
                video_src = f"{base_url}?token={token}"
            elif lesson.raw_video:
                video_kind = 'direct'
                video_src = lesson.raw_video.url
            elif lesson.video_url:
                video_kind = 'direct'
                video_src = lesson.video_url

        file_url = ''
        if lesson.file_upload and lesson_unlocked:
            try:
                file_url = lesson.file_upload.url
            except Exception:
                file_url = ''

        return {
            'id': lesson.id,
            'order': lesson.order,
            'title': lesson.title,
            'lesson_type': lesson.lesson_type,
            'type_label': lesson.get_lesson_type_display() or lesson.get_content_type_display(),
            'summary': lesson.text_content,
            'is_free_preview': lesson.is_free_preview,
            'min_watch_percent': lesson.min_watch_percent,
            'duration_seconds': lesson.duration_seconds,
            'duration_display': _format_duration(lesson.duration_seconds),
            'watched_seconds': watched_seconds,
            'last_position_seconds': last_position_seconds,
            'is_completed': is_completed,
            'is_unlocked': lesson_unlocked,
            'drip_locked': drip_locked,
            'drip_unlock_days': drip_unlock_days,
            'can_open': can_open,
            'has_video': has_video,
            'video_kind': video_kind,
            'video_src': video_src,
            'file_url': file_url,
            'detail_url': reverse('lessons:lesson_detail', args=[course.slug, lesson.id]),
            'mark_completed_url': reverse('lessons:mark_completed_api', args=[lesson.id]),
            'heartbeat_url': reverse('lessons:heartbeat_api', args=[lesson.id]),
        }

    def _serialize_quiz(quiz, section_unlocked):
        is_passed = quiz.id in passed_quiz_ids
        return {
            'id': quiz.id,
            'title': quiz.title,
            'description': quiz.description,
            'time_limit_minutes': quiz.time_limit_minutes,
            'pass_mark_percent': quiz.pass_mark_percent,
            'total_questions': quiz.questions.count(),
            'is_passed': is_passed,
            'best_score': best_quiz_scores.get(quiz.id),
            'is_unlocked': has_course_access and section_unlocked,
            'detail_url': reverse('quizzes:quiz_detail', args=[quiz.id]),
        }

    sections = []
    previous_modules_completed = True
    blocking_module_info = None
    first_expanded_assigned = False

    total_lessons = 0
    completed_lessons = 0
    total_quizzes = 0
    completed_quizzes = 0

    for idx, module in enumerate(modules, start=1):
        mod_lessons = list(module.lessons.all().order_by('order', 'id'))
        mod_quizzes = list(module.quizzes.all().order_by('created_at', 'id'))

        done_count, item_count, mod_completed = _get_module_completion_counts(
            module, completed_lesson_ids, passed_quiz_ids
        )
        mod_unlocked = is_privileged or (has_course_access and previous_modules_completed)
        lock_reason = ""
        if has_course_access and not mod_unlocked and blocking_module_info:
            b_title, b_done, b_total = blocking_module_info
            lock_reason = f"Complete \"{b_title}\" ({b_done}/{b_total} completed) to unlock this module."

        serialized_lessons = [_serialize_lesson(l, mod_unlocked) for l in mod_lessons]
        serialized_quizzes = [_serialize_quiz(q, mod_unlocked) for q in mod_quizzes]

        lesson_done_in_mod = sum(1 for item in serialized_lessons if item['is_completed'])
        quiz_done_in_mod = sum(1 for item in serialized_quizzes if item['is_passed'])

        total_lessons += len(serialized_lessons)
        completed_lessons += lesson_done_in_mod
        total_quizzes += len(serialized_quizzes)
        completed_quizzes += quiz_done_in_mod

        progress_percent = int(round((done_count / item_count) * 100)) if item_count > 0 else 0

        # Auto-expand the first unlocked incomplete module (or first module)
        expand_by_default = False
        if not first_expanded_assigned and mod_unlocked and not mod_completed:
            expand_by_default = True
            first_expanded_assigned = True

        sections.append({
            'key': f"module-{module.id}",
            'id': module.id,
            'is_standalone': False,
            'number': idx,
            'title': module.title,
            'description': module.description,
            'lessons': serialized_lessons,
            'quizzes': serialized_quizzes,
            'lessons_count': len(serialized_lessons),
            'quizzes_count': len(serialized_quizzes),
            'completed_count': done_count,
            'total_count': item_count,
            'progress_percent': progress_percent,
            'is_completed': mod_completed,
            'is_unlocked': mod_unlocked,
            'lock_reason': lock_reason,
            'expand_by_default': expand_by_default,
        })

        if previous_modules_completed and not mod_completed:
            blocking_module_info = (module.title, done_count, item_count)
        previous_modules_completed = previous_modules_completed and mod_completed

    # Standalone lessons / quizzes (module=None)
    if standalone_lessons or standalone_quizzes:
        s_lessons = [_serialize_lesson(l, True) for l in standalone_lessons]
        s_quizzes = [_serialize_quiz(q, True) for q in standalone_quizzes]
        s_done = sum(1 for l in s_lessons if l['is_completed']) + sum(1 for q in s_quizzes if q['is_passed'])
        s_total = len(s_lessons) + len(s_quizzes)

        total_lessons += len(s_lessons)
        completed_lessons += sum(1 for l in s_lessons if l['is_completed'])
        total_quizzes += len(s_quizzes)
        completed_quizzes += sum(1 for q in s_quizzes if q['is_passed'])

        s_completed = s_total > 0 and s_done >= s_total
        s_percent = int(round((s_done / s_total) * 100)) if s_total > 0 else 0
        expand_by_default = not first_expanded_assigned
        if expand_by_default:
            first_expanded_assigned = True

        sections.append({
            'key': 'module-core',
            'id': None,
            'is_standalone': True,
            'number': len(modules) + 1 if modules else 1,
            'title': 'Additional Lectures & Resources' if modules else 'Core Course Lectures',
            'description': 'Structured course lectures and learning materials.' if not modules else 'Unassigned course lectures and assessments.',
            'lessons': s_lessons,
            'quizzes': s_quizzes,
            'lessons_count': len(s_lessons),
            'quizzes_count': len(s_quizzes),
            'completed_count': s_done,
            'total_count': s_total,
            'progress_percent': s_percent,
            'is_completed': s_completed,
            'is_unlocked': has_course_access,
            'lock_reason': '',
            'expand_by_default': expand_by_default,
        })

    if not first_expanded_assigned and sections:
        sections[0]['expand_by_default'] = True

    total_items = total_lessons + total_quizzes
    completed_items = completed_lessons + completed_quizzes
    overall_progress_percent = int(round((completed_items / total_items) * 100)) if total_items > 0 else 0
    completed_modules_count = sum(1 for s in sections if not s['is_standalone'] and s['is_completed'])

    # Find first playable unlocked video for quick-play button
    first_playable_lesson = None
    for sec in sections:
        if not sec['is_unlocked']:
            continue
        for les in sec['lessons']:
            if les['has_video'] and les['video_src']:
                first_playable_lesson = les
                break
        if first_playable_lesson:
            break

    return {
        'sections': sections,
        'total_modules': len(modules),
        'completed_modules': completed_modules_count,
        'total_lessons': total_lessons,
        'completed_lessons': completed_lessons,
        'total_quizzes': total_quizzes,
        'completed_quizzes': completed_quizzes,
        'total_items': total_items,
        'completed_items': completed_items,
        'overall_progress_percent': overall_progress_percent,
        'has_course_access': has_course_access,
        'first_playable_lesson': first_playable_lesson,
    }
