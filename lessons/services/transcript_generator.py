import math
import re

from django.db import transaction

from lessons.models import LessonTranscriptSegment


_TIMED_RANGE_RE = re.compile(
    r'^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)'
)
_LINE_PREFIX_TS_RE = re.compile(
    r'^\s*[\[\(]?((?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?)[\]\)]?\s*(?:[-–:|]\s*)?(.+?)\s*$'
)


def parse_timestamp_to_seconds(ts_str):
    """Parse HH:MM:SS.mmm or MM:SS.mmm or raw seconds into float seconds."""
    cleaned = ts_str.strip().replace(',', '.')
    parts = cleaned.split(':')
    try:
        if len(parts) == 3:
            return round(float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]), 2)
        if len(parts) == 2:
            return round(float(parts[0]) * 60 + float(parts[1]), 2)
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return 0.0


def _split_plain_sentences(raw_text):
    """Split raw prose/script cleanly into timed readable transcript cue phrases."""
    raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    sentences = []
    for line in raw_lines:
        parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', line) if p.strip()]
        for part in parts:
            words = part.split()
            if len(words) <= 18:
                sentences.append(part)
            else:
                for i in range(0, len(words), 14):
                    chunk = ' '.join(words[i:i + 14]).strip()
                    if chunk:
                        sentences.append(chunk)
    return sentences


def parse_transcript_lines(raw_text, total_duration_seconds=0, target_duration_seconds=None):
    """
    Parse VTT/SRT, `[mm:ss] text`, or plain text into structured timed cues.
    If target_duration_seconds is provided, stretches or compacts cues cleanly to match it.
    """
    text = (raw_text or '').strip()
    if not text:
        return []

    lines = text.splitlines()
    parsed = []

    # 1. Try SRT / WebVTT cue parsing
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.upper().startswith('WEBVTT') or line.isdigit():
            i += 1
            continue
        match = _TIMED_RANGE_RE.match(line)
        if match:
            start_s = parse_timestamp_to_seconds(match.group(1))
            end_s = parse_timestamp_to_seconds(match.group(2))
            cue_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                cue_lines.append(lines[i].strip())
                i += 1
            cue_text = ' '.join(cue_lines).strip()
            if cue_text:
                if end_s <= start_s:
                    end_s = round(start_s + 4.0, 2)
                parsed.append({
                    'order': len(parsed) + 1,
                    'start_seconds': start_s,
                    'end_seconds': end_s,
                    'text': cue_text,
                })
        else:
            i += 1

    if parsed:
        if target_duration_seconds and target_duration_seconds > 0:
            return _rescale_cues_to_duration(parsed, float(target_duration_seconds))
        return parsed

    # 2. Try [mm:ss] or mm:ss prefixed single-line cues
    prefixed = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        m = _LINE_PREFIX_TS_RE.match(stripped)
        if m:
            prefixed.append((parse_timestamp_to_seconds(m.group(1)), m.group(2).strip()))

    if prefixed and len(prefixed) == len([l for l in lines if l.strip()]):
        prefixed.sort(key=lambda item: item[0])
        cues = []
        total_ref = float(target_duration_seconds or total_duration_seconds or 0)
        for idx, (start_s, cue_text) in enumerate(prefixed):
            if idx + 1 < len(prefixed):
                end_s = max(prefixed[idx + 1][0], start_s + 2.0)
            else:
                end_s = max(total_ref, start_s + 5.0)
            cues.append({
                'order': idx + 1,
                'start_seconds': round(start_s, 2),
                'end_seconds': round(end_s, 2),
                'text': cue_text,
            })
        if target_duration_seconds and target_duration_seconds > 0:
            return _rescale_cues_to_duration(cues, float(target_duration_seconds))
        return cues

    # 3. Plain text -> proportional timing across video duration or speech rate (~2.4 words/sec)
    phrases = _split_plain_sentences(text)
    if not phrases:
        return []

    weights = [max(len(p.split()), 2) for p in phrases]
    total_words = sum(weights)

    if target_duration_seconds and target_duration_seconds > 0:
        span = float(target_duration_seconds)
    elif total_duration_seconds and total_duration_seconds > 0:
        span = float(total_duration_seconds)
    else:
        span = max(round(total_words / 2.4, 2), len(phrases) * 4.0)

    cues = []
    cursor = 0.0
    for idx, (phrase, w) in enumerate(zip(phrases, weights), start=1):
        seg_dur = span * (w / total_words)
        end_s = span if idx == len(phrases) else round(cursor + seg_dur, 2)
        cues.append({
            'order': idx,
            'start_seconds': round(cursor, 2),
            'end_seconds': max(end_s, round(cursor + 0.5, 2)),
            'text': phrase,
        })
        cursor = end_s

    return cues


def _rescale_cues_to_duration(cues, target_duration):
    """Rescale timed cues cleanly so the final transcript cue ends at target_duration."""
    if not cues or target_duration <= 0:
        return cues
    current_max = max(c['end_seconds'] for c in cues)
    if current_max <= 0:
        return cues
    ratio = target_duration / current_max
    scaled = []
    for idx, cue in enumerate(cues, start=1):
        s = round(cue['start_seconds'] * ratio, 2)
        e = round(target_duration, 2) if idx == len(cues) else round(cue['end_seconds'] * ratio, 2)
        scaled.append({
            'order': cue.get('order', idx),
            'start_seconds': s,
            'end_seconds': max(e, round(s + 0.4, 2)),
            'text': cue['text'],
        })
    return scaled


def _build_default_cues_for_lesson(lesson, duration_seconds):
    """Generate clean structured outline cues when no script text exists yet."""
    total = max(int(duration_seconds or 30), 15)
    step_count = min(max(math.ceil(total / 15), 3), 8)
    step_len = round(total / step_count, 2)
    cues = []
    for idx in range(step_count):
        start_s = round(idx * step_len, 2)
        end_s = float(total) if idx == step_count - 1 else round((idx + 1) * step_len, 2)
        if idx == 0:
            label = f"Introduction and overview of {lesson.title}."
        elif idx == step_count - 1:
            label = f"Key takeaways and summary for {lesson.title}."
        else:
            label = f"Section {idx + 1}: Core concepts and walkthrough."
        cues.append({
            'order': idx + 1,
            'start_seconds': start_s,
            'end_seconds': end_s,
            'text': label,
        })
    return cues


def generate_lesson_transcript(lesson, raw_text=None, target_duration_seconds=None, create_default=False):
    """
    Generate or regenerate timestamped transcript segments for a lesson and sync
    `lesson.transcript_duration_seconds` so the web player aligns playback length
    and supports click-a-line seeking.
    """
    source_text = (raw_text if raw_text is not None else lesson.text_content or '').strip()
    dur = int(target_duration_seconds or lesson.duration_seconds or 0)

    cues = parse_transcript_lines(
        source_text,
        total_duration_seconds=lesson.duration_seconds or 0,
        target_duration_seconds=target_duration_seconds,
    )

    if not cues and create_default:
        cues = _build_default_cues_for_lesson(lesson, dur)

    if not cues:
        return []

    max_end = max(int(math.ceil(c['end_seconds'])) for c in cues)

    with transaction.atomic():
        LessonTranscriptSegment.objects.filter(lesson=lesson).delete()
        segments = [
            LessonTranscriptSegment(
                lesson=lesson,
                order=cue['order'],
                start_seconds=cue['start_seconds'],
                end_seconds=cue['end_seconds'],
                text=cue['text'],
            )
            for cue in cues
        ]
        created = LessonTranscriptSegment.objects.bulk_create(segments)

        update_fields = ['transcript_duration_seconds']
        lesson.transcript_duration_seconds = max_end
        if not lesson.duration_seconds and max_end > 0:
            lesson.duration_seconds = max_end
            update_fields.append('duration_seconds')
        if raw_text is not None and raw_text.strip():
            lesson.text_content = raw_text.strip()
            update_fields.append('text_content')
        lesson.save(update_fields=update_fields)

    return created
