import json
import re
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import Category, Course
from enrollments.models import Enrollment
from lessons.models import Lesson, LessonProgress, LessonTranscriptSegment
from lessons.services.hls_transcoder import (
    QUALITY_TIERS,
    _parse_mp4_metadata,
    transcode_lesson_video,
)
from lessons.services.transcript_generator import (
    generate_lesson_transcript,
    parse_transcript_lines,
)
from lessons.views import get_hls_signer

User = get_user_model()


def _mp4_box(box_type, payload):
    """Build a single ISO BMFF box header + payload."""
    return struct.pack('>I4s', 8 + len(payload), box_type.encode('ascii')) + payload


def _build_minimal_mp4(duration_seconds=120, width=1920, height=1080):
    """Construct minimal valid MP4 metadata boxes (ftyp + moov/mvhd + trak/tkhd)."""
    ftyp = _mp4_box('ftyp', b'isom\x00\x00\x02\x00isomiso2mp41')
    mvhd_payload = b'\x00' * 12 + struct.pack('>II', 1000, duration_seconds * 1000)
    mvhd = _mp4_box('mvhd', mvhd_payload)
    tkhd_payload = b'\x00' * 76 + struct.pack('>II', width << 16, height << 16)
    tkhd = _mp4_box('tkhd', tkhd_payload)
    trak = _mp4_box('trak', tkhd)
    moov = _mp4_box('moov', mvhd + trak)
    return ftyp + moov


class BaseLessonFeatureTestCase(TestCase):
    """Shared isolated temporary media/private_media environment for lesson tests."""

    def setUp(self):
        super().setUp()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)

        self._settings_override = override_settings(
            MEDIA_ROOT=self._tmp_dir.name,
            PRIVATE_MEDIA_ROOT=self._tmp_dir.name,
        )
        self._settings_override.enable()
        self.addCleanup(self._settings_override.disable)

        storage = Lesson._meta.get_field('raw_video').storage
        orig_location = getattr(storage, 'location', None)
        orig_base = getattr(storage, 'base_location', None)
        orig_priv = getattr(storage, '_location', None)
        storage.base_location = self._tmp_dir.name
        storage._location = self._tmp_dir.name
        if 'location' in storage.__dict__:
            storage.__dict__['location'] = self._tmp_dir.name

        def _restore_storage():
            storage.base_location = orig_base
            storage._location = orig_priv
            if orig_location is not None and 'location' in storage.__dict__:
                storage.__dict__['location'] = orig_location

        self.addCleanup(_restore_storage)

        self.instructor = User.objects.create_user(
            username='inst_video',
            email='inst_video@example.com',
            password='Password123!',
            role=User.Role.INSTRUCTOR,
        )
        self.student = User.objects.create_user(
            username='stud_video',
            email='stud_video@example.com',
            password='Password123!',
            role=User.Role.STUDENT,
        )
        self.outsider = User.objects.create_user(
            username='out_video',
            email='out_video@example.com',
            password='Password123!',
            role=User.Role.STUDENT,
        )
        self.category = Category.objects.create(name='Video Engineering', slug='video-engineering')
        self.course = Course.objects.create(
            title='Adaptive Streaming 101',
            slug='adaptive-streaming-101',
            description='Learn HLS and transcript sync.',
            instructor=self.instructor,
            category=self.category,
            status=Course.Status.PUBLISHED,
            is_free=True,
        )
        Enrollment.objects.create(student=self.student, course=self.course)


class VideoTranscodingAndStreamTests(BaseLessonFeatureTestCase):
    """Verify MP4 probing, multi-quality HLS packaging, and download-protected Range streaming."""

    def test_parse_mp4_metadata_extracts_duration_and_dimensions(self):
        video_file = Path(self._tmp_dir.name) / 'probe_sample.mp4'
        video_file.write_bytes(_build_minimal_mp4(duration_seconds=145, width=1920, height=1080))
        meta = _parse_mp4_metadata(video_file)
        self.assertEqual(meta['duration_seconds'], 145)
        self.assertEqual(meta['width'], 1920)
        self.assertEqual(meta['height'], 1080)

    def test_transcode_lesson_video_fallback_without_ffmpeg(self):
        upload = SimpleUploadedFile('lecture.mp4', _build_minimal_mp4(duration_seconds=95), content_type='video/mp4')
        lesson = Lesson.objects.create(
            course=self.course,
            title='Direct Upload Video',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            raw_video=upload,
        )

        with patch('lessons.services.hls_transcoder._get_ffmpeg_binary', return_value=None):
            result = transcode_lesson_video(lesson)

        lesson.refresh_from_db()
        self.assertIsNone(result)
        self.assertEqual(lesson.transcode_status, Lesson.TranscodeStatus.STREAM_ONLY)
        self.assertEqual(lesson.hls_playlist_relpath, '')
        self.assertEqual(lesson.duration_seconds, 95)
        self.assertEqual([q['label'] for q in lesson.video_qualities], ['1080p', '720p', '480p'])
        self.assertTrue(all(q['encoded'] is False for q in lesson.video_qualities))
        self.assertTrue((Path(self._tmp_dir.name) / 'hls' / str(lesson.id) / 'key.bin').exists())

    def test_transcode_lesson_video_multi_quality_with_mocked_ffmpeg(self):
        upload = SimpleUploadedFile('master.mp4', _build_minimal_mp4(duration_seconds=180), content_type='video/mp4')
        lesson = Lesson.objects.create(
            course=self.course,
            title='Multi-Quality Lecture',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            raw_video=upload,
        )

        def fake_subprocess_run(cmd, check=True, stdout=None, stderr=None):
            out_m3u8 = Path(cmd[-1])
            tier_dir = out_m3u8.parent
            tier_dir.mkdir(parents=True, exist_ok=True)
            (tier_dir / 'segment_000.ts').write_bytes(b'MOCK_TS_ENCRYPTED_PAYLOAD')
            out_m3u8.write_text(
                '#EXTM3U\n'
                '#EXT-X-VERSION:3\n'
                '#EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x' + lesson.aes_iv + '\n'
                '#EXTINF:6.0,\n'
                'segment_000.ts\n'
                '#EXT-X-ENDLIST\n',
                encoding='utf-8',
            )
            return None

        with patch('lessons.services.hls_transcoder._get_ffmpeg_binary', return_value='/usr/bin/ffmpeg'), \
             patch('lessons.services.hls_transcoder.subprocess.run', side_effect=fake_subprocess_run) as mock_run:
            relpath = transcode_lesson_video(lesson)

        self.assertEqual(mock_run.call_count, len(QUALITY_TIERS))
        lesson.refresh_from_db()
        self.assertEqual(lesson.transcode_status, Lesson.TranscodeStatus.READY)
        self.assertEqual(relpath, f'hls/{lesson.id}/master.m3u8')
        self.assertEqual(lesson.hls_playlist_relpath, f'hls/{lesson.id}/master.m3u8')
        self.assertEqual(len(lesson.video_qualities), 3)
        self.assertTrue(all(q['encoded'] is True for q in lesson.video_qualities))

        master_file = Path(self._tmp_dir.name) / relpath
        master_text = master_file.read_text(encoding='utf-8')
        self.assertIn('1080p/index.m3u8', master_text)
        self.assertIn('720p/index.m3u8', master_text)
        self.assertIn('480p/index.m3u8', master_text)

    def test_hls_multi_quality_manifest_variant_and_segment_security(self):
        upload = SimpleUploadedFile('hls_src.mp4', _build_minimal_mp4(duration_seconds=60), content_type='video/mp4')
        lesson = Lesson.objects.create(
            course=self.course,
            title='Secured HLS Lecture',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            raw_video=upload,
        )

        def fake_run(cmd, check=True, stdout=None, stderr=None):
            out_m3u8 = Path(cmd[-1])
            tier_dir = out_m3u8.parent
            (tier_dir / 'segment_000.ts').write_bytes(b'SECURED_TS_BYTES')
            out_m3u8.write_text(
                '#EXTM3U\n'
                '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
                '#EXTINF:6.0,\n'
                'segment_000.ts\n'
                '#EXT-X-ENDLIST\n',
                encoding='utf-8',
            )
            return None

        with patch('lessons.services.hls_transcoder._get_ffmpeg_binary', return_value='/usr/bin/ffmpeg'), \
             patch('lessons.services.hls_transcoder.subprocess.run', side_effect=fake_run):
            transcode_lesson_video(lesson)

        manifest_url = reverse('lessons:hls_manifest', args=[self.course.slug, lesson.id])
        variant_url = reverse('lessons:hls_variant_manifest', args=[self.course.slug, lesson.id, '720p'])
        seg_url = reverse('lessons:hls_variant_segment', args=[self.course.slug, lesson.id, '720p', 'segment_000.ts'])

        token = get_hls_signer().sign(f'{self.student.id}:{lesson.id}')

        # Missing token and unenrolled access must fail
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(manifest_url).status_code, 403)
        self.client.force_login(self.outsider)
        out_tok = get_hls_signer().sign(f'{self.outsider.id}:{lesson.id}')
        self.assertEqual(self.client.get(f'{manifest_url}?token={out_tok}').status_code, 403)

        # Enrolled student with signed token gets rewritten multi-quality playlists and segment
        self.client.force_login(self.student)
        master_resp = self.client.get(f'{manifest_url}?token={token}')
        self.assertEqual(master_resp.status_code, 200)
        master_body = master_resp.content.decode('utf-8')
        self.assertIn(f'/hls/1080p/manifest.m3u8?token={token}', master_body)
        self.assertIn(f'/hls/720p/manifest.m3u8?token={token}', master_body)
        self.assertIn(f'/hls/480p/manifest.m3u8?token={token}', master_body)

        var_resp = self.client.get(f'{variant_url}?token={token}')
        self.assertEqual(var_resp.status_code, 200)
        var_body = var_resp.content.decode('utf-8')
        self.assertIn(f'hls/key/?token={token}', var_body)
        self.assertIn(f'hls/720p/segment/segment_000.ts?token={token}', var_body)

        seg_resp = self.client.get(f'{seg_url}?token={token}')
        self.assertEqual(seg_resp.status_code, 200)
        self.assertEqual(b''.join(seg_resp.streaming_content), b'SECURED_TS_BYTES')

    def test_protected_stream_supports_range_and_blocks_unauthorized(self):
        payload = _build_minimal_mp4(duration_seconds=30) + b'0123456789ABCDEF'
        upload = SimpleUploadedFile('range_video.mp4', payload, content_type='video/mp4')
        lesson = Lesson.objects.create(
            course=self.course,
            title='Range Protected Lecture',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            raw_video=upload,
        )
        stream_url = reverse('lessons:protected_stream', args=[self.course.slug, lesson.id])
        token = get_hls_signer().sign(f'{self.student.id}:{lesson.id}')

        # Unauthorized without login / unenrolled / missing token
        self.assertEqual(self.client.get(stream_url).status_code, 302)
        self.client.force_login(self.outsider)
        bad_tok = get_hls_signer().sign(f'{self.outsider.id}:{lesson.id}')
        self.assertEqual(self.client.get(f'{stream_url}?token={bad_tok}').status_code, 403)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(stream_url).status_code, 403)

        # Full stream request returns 200 with no-store & byte range support
        full_resp = self.client.get(f'{stream_url}?token={token}')
        self.assertEqual(full_resp.status_code, 200)
        self.assertEqual(full_resp['Accept-Ranges'], 'bytes')
        self.assertIn('no-store', full_resp['Cache-Control'])
        self.assertEqual(b''.join(full_resp.streaming_content), payload)

        # HTTP Range request returns 206 Partial Content
        part_resp = self.client.get(f'{stream_url}?token={token}', HTTP_RANGE='bytes=0-15')
        self.assertEqual(part_resp.status_code, 206)
        self.assertEqual(part_resp['Content-Range'], f'bytes 0-15/{len(payload)}')
        self.assertEqual(b''.join(part_resp.streaming_content), payload[:16])


class TranscriptSyncAndPlayerTemplateTests(BaseLessonFeatureTestCase):
    """Verify transcript timing manipulation, heartbeat completion sync, and custom player UI."""

    def test_parse_and_rescale_transcript_timing(self):
        raw_cues = (
            '[00:00] Welcome to systems architecture.\n'
            '[00:15] Understanding latency and bandwidth.\n'
            '[00:30] Summary and next steps.'
        )
        parsed = parse_transcript_lines(raw_cues, total_duration_seconds=45, target_duration_seconds=90)
        self.assertEqual(len(parsed), 3)
        self.assertAlmostEqual(parsed[0]['start_seconds'], 0.0, places=1)
        self.assertAlmostEqual(parsed[-1]['end_seconds'], 90.0, places=1)

        srt_cues = (
            '1\n'
            '00:00:02,000 --> 00:00:10,000\n'
            'Introduction to HLS segments.\n\n'
            '2\n'
            '00:00:10,000 --> 00:00:20,000\n'
            'AES-128 content protection.'
        )
        parsed_srt = parse_transcript_lines(srt_cues)
        self.assertEqual(len(parsed_srt), 2)
        self.assertEqual(parsed_srt[0]['start_seconds'], 2.0)
        self.assertEqual(parsed_srt[1]['text'], 'AES-128 content protection.')

    def test_generate_transcript_api_permissions_and_length_manipulation(self):
        lesson = Lesson.objects.create(
            course=self.course,
            title='Transcript Sync Lecture',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            duration_seconds=120,
        )
        api_url = reverse('lessons:generate_transcript_api', args=[lesson.id])

        # Students cannot regenerate lesson transcripts
        self.client.force_login(self.student)
        res_forbidden = self.client.post(
            api_url,
            data=json.dumps({'raw_text': 'Line one\nLine two', 'target_duration_seconds': 90}),
            content_type='application/json',
        )
        self.assertEqual(res_forbidden.status_code, 403)

        # Instructor regenerates transcript with custom manipulated length = 90s
        self.client.force_login(self.instructor)
        res_ok = self.client.post(
            api_url,
            data=json.dumps({
                'raw_text': 'Opening overview\nAdaptive bitrate streaming\nConclusion',
                'target_duration_seconds': 90,
            }),
            content_type='application/json',
        )
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['transcript_duration_seconds'], 90)
        self.assertEqual(len(data['cues']), 3)
        self.assertAlmostEqual(data['cues'][-1]['end'], 90.0, places=1)

        lesson.refresh_from_db()
        self.assertEqual(lesson.transcript_duration_seconds, 90)
        self.assertEqual(lesson.transcript_segments.count(), 3)

    def test_heartbeat_respects_transcript_duration_seconds(self):
        lesson = Lesson.objects.create(
            course=self.course,
            title='Short Transcript Timeline',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            duration_seconds=200,
            transcript_duration_seconds=40,
            min_watch_percent=85,
        )
        hb_url = reverse('lessons:heartbeat_api', args=[lesson.id])
        self.client.force_login(self.student)

        # 85% of transcript_duration_seconds=40 is 34s -> send pulses totaling 36s (well below 170s from 200s)
        for pos in (12, 24, 36):
            resp = self.client.post(
                hb_url,
                data=json.dumps({'current_position': pos, 'delta_watched': 12}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)

        progress = LessonProgress.objects.get(student=self.student, lesson=lesson)
        self.assertTrue(progress.is_completed)

    def test_lesson_detail_renders_custom_player_and_clickable_transcript(self):
        upload = SimpleUploadedFile('player_ui.mp4', _build_minimal_mp4(duration_seconds=60), content_type='video/mp4')
        lesson = Lesson.objects.create(
            course=self.course,
            title='Custom Player Lesson',
            order=1,
            lesson_type=Lesson.LessonType.VIDEO,
            content_type=Lesson.ContentType.VIDEO,
            raw_video=upload,
            text_content='[00:00] First line\n[00:30] Second line',
            duration_seconds=60,
        )
        with patch('lessons.services.hls_transcoder._get_ffmpeg_binary', return_value=None):
            transcode_lesson_video(lesson)
        generate_lesson_transcript(lesson)

        detail_url = reverse('lessons:lesson_detail', args=[self.course.slug, lesson.id])
        self.client.force_login(self.student)
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        # Static architecture and custom structured player controls
        self.assertIn('css/lesson_detail.css', html)
        self.assertIn('js/lms-player.js', html)
        self.assertIn('js/video-protection.js', html)
        self.assertIn('id="lms-player-shell"', html)
        self.assertIn('id="lms-controls-dock"', html)
        self.assertIn('id="btn-player-play"', html)
        self.assertIn('id="select-player-quality"', html)
        self.assertIn('id="select-player-speed"', html)
        self.assertIn('id="lms-seekbar-outer"', html)
        self.assertIn('id="lms-transcript-panel"', html)
        self.assertIn('class="transcript-cue-item', html)
        self.assertIn('data-start="0.0"', html)
        self.assertIn('data-start="30.0"', html)
        self.assertIn('id="chk-transcript-sync"', html)
        # Protected token stream URL (not raw unauthenticated media URL)
        self.assertIn('/stream/?token=', html)
        self.assertNotIn('<style', html.lower())
        self.assertIsNone(re.search(r'\son[a-z]+\s*=', html, flags=re.IGNORECASE))
        # Student should not render instructor transcript generation controls
        self.assertNotIn('id="btn-generate-transcript"', html)

        # Instructor sees transcript generator controls
        self.client.force_login(self.instructor)
        inst_html = self.client.get(detail_url).content.decode('utf-8')
        self.assertIn('id="btn-generate-transcript"', inst_html)
