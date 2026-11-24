import json
import os
import secrets
import shutil
import struct
import subprocess
from pathlib import Path

from django.conf import settings


QUALITY_TIERS = [
    {
        'label': '1080p',
        'width': 1920,
        'height': 1080,
        'video_bitrate': '5000k',
        'maxrate': '5350k',
        'bufsize': '7500k',
        'audio_bitrate': '192k',
        'bandwidth': 5000000,
    },
    {
        'label': '720p',
        'width': 1280,
        'height': 720,
        'video_bitrate': '2800k',
        'maxrate': '2996k',
        'bufsize': '4200k',
        'audio_bitrate': '128k',
        'bandwidth': 2800000,
    },
    {
        'label': '480p',
        'width': 854,
        'height': 480,
        'video_bitrate': '1400k',
        'maxrate': '1498k',
        'bufsize': '2100k',
        'audio_bitrate': '96k',
        'bandwidth': 1400000,
    },
]

ALLOWED_QUALITIES = {q['label'] for q in QUALITY_TIERS}


def get_private_media_root():
    return getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')


def get_cdn_media_url(relative_path):
    """Build optional global CDN URL prefix if VIDEO_CDN_BASE_URL is configured."""
    base = getattr(settings, 'VIDEO_CDN_BASE_URL', '') or ''
    base = base.strip().rstrip('/')
    if not base:
        return ''
    return f"{base}/{relative_path.lstrip('/')}"


def generate_aes_key():
    return secrets.token_bytes(16)


def generate_aes_iv():
    return secrets.token_hex(16)


def _iter_mp4_boxes(fh, start_offset, end_offset):
    """Yield (box_type, payload_start, box_end) for ISO BMFF atoms within [start_offset, end_offset)."""
    pos = start_offset
    while pos + 8 <= end_offset:
        fh.seek(pos)
        header = fh.read(8)
        if len(header) < 8:
            break
        size, box_type = struct.unpack('>I4s', header)
        header_len = 8
        if size == 1:
            ext = fh.read(8)
            if len(ext) < 8:
                break
            size = struct.unpack('>Q', ext)[0]
            header_len = 16
        elif size == 0:
            size = end_offset - pos

        if size < header_len or pos + size > end_offset:
            break

        yield box_type.decode('latin-1', errors='replace'), pos + header_len, pos + size
        pos += size


def _parse_mp4_metadata(video_path):
    """Pure-Python MP4/MOV duration and resolution parser via mvhd and tkhd boxes."""
    meta = {'duration_seconds': 0, 'width': 0, 'height': 0}
    try:
        file_size = os.path.getsize(video_path)
        with open(video_path, 'rb') as fh:
            for top_type, top_payload, top_end in _iter_mp4_boxes(fh, 0, file_size):
                if top_type == 'moov':
                    for moov_type, m_payload, m_end in _iter_mp4_boxes(fh, top_payload, top_end):
                        if moov_type == 'mvhd' and m_end - m_payload >= 20:
                            fh.seek(m_payload)
                            version = struct.unpack('>B', fh.read(1))[0]
                            if version == 0 and m_end - m_payload >= 20:
                                fh.seek(m_payload + 12)
                                timescale, duration = struct.unpack('>II', fh.read(8))
                                if timescale > 0:
                                    meta['duration_seconds'] = max(meta['duration_seconds'], int(round(duration / timescale)))
                            elif version == 1 and m_end - m_payload >= 32:
                                fh.seek(m_payload + 20)
                                timescale, duration = struct.unpack('>IQ', fh.read(12))
                                if timescale > 0:
                                    meta['duration_seconds'] = max(meta['duration_seconds'], int(round(duration / timescale)))
                        elif moov_type == 'trak':
                            for trak_type, t_payload, t_end in _iter_mp4_boxes(fh, m_payload, m_end):
                                if trak_type == 'tkhd':
                                    fh.seek(t_payload)
                                    ver = struct.unpack('>B', fh.read(1))[0]
                                    w_offset = 76 if ver == 0 else 88
                                    if t_end - t_payload >= w_offset + 8:
                                        fh.seek(t_payload + w_offset)
                                        w_fixed, h_fixed = struct.unpack('>II', fh.read(8))
                                        width = w_fixed >> 16
                                        height = h_fixed >> 16
                                        if width > meta['width'] and height > meta['height']:
                                            meta['width'] = width
                                            meta['height'] = height
                    break
    except Exception:
        pass
    return meta


def probe_video_metadata(video_path):
    """Inspect uploaded video duration and pixel resolution using ffprobe or pure-Python MP4 parser."""
    path_str = str(Path(video_path).resolve())
    ffprobe_bin = getattr(settings, 'FFPROBE_BINARY', None) or shutil.which('ffprobe')
    if ffprobe_bin:
        try:
            cmd = [
                ffprobe_bin,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                path_str,
            ]
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            data = json.loads(proc.stdout.decode('utf-8', errors='replace'))
            duration = float(data.get('format', {}).get('duration') or 0)
            width = 0
            height = 0
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = int(stream.get('width') or 0)
                    height = int(stream.get('height') or 0)
                    break
            return {
                'duration_seconds': max(int(round(duration)), 0),
                'width': width,
                'height': height,
            }
        except Exception:
            pass

    return _parse_mp4_metadata(path_str)


def _get_ffmpeg_binary():
    configured = getattr(settings, 'FFMPEG_BINARY', None)
    if configured and shutil.which(str(configured)):
        return str(configured)
    return shutil.which('ffmpeg')


def transcode_lesson_video(lesson):
    """
    Compress uploaded lesson raw_video into multi-quality adaptive HLS streams
    (1080p, 720p, 480p) encrypted with AES-128 keys for download-protected global streaming.
    If FFmpeg is not available on the host, extracts video metadata cleanly and configures
    the lesson for protected HTTP Range streaming without breaking browser playback.
    """
    if not lesson.raw_video:
        return None

    try:
        raw_path = Path(lesson.raw_video.path)
    except Exception:
        return None

    if not raw_path.exists():
        return None

    meta = probe_video_metadata(raw_path)
    if meta['duration_seconds'] > 0 and not lesson.duration_seconds:
        lesson.duration_seconds = meta['duration_seconds']

    if not lesson.aes_key:
        lesson.aes_key = generate_aes_key()
    if not lesson.aes_iv:
        lesson.aes_iv = generate_aes_iv()

    private_root = Path(get_private_media_root())
    hls_dir = private_root / 'hls' / str(lesson.id)
    hls_dir.mkdir(parents=True, exist_ok=True)
    key_file = hls_dir / 'key.bin'

    with open(key_file, 'wb') as f:
        f.write(lesson.aes_key)

    ffmpeg_bin = _get_ffmpeg_binary()
    if ffmpeg_bin:
        generated_tiers = []
        master_lines = ['#EXTM3U', '#EXT-X-VERSION:3']

        for tier in QUALITY_TIERS:
            label = tier['label']
            tier_dir = hls_dir / label
            tier_dir.mkdir(parents=True, exist_ok=True)
            tier_m3u8 = tier_dir / 'index.m3u8'
            key_info_file = tier_dir / 'key_info.txt'

            with open(key_info_file, 'w', encoding='utf-8') as kf:
                kf.write(f"key.bin\n{key_file.resolve()}\n{lesson.aes_iv}\n")

            cmd = [
                ffmpeg_bin,
                '-y',
                '-i', str(raw_path.resolve()),
                '-vf', f"scale=-2:{tier['height']}",
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-b:v', tier['video_bitrate'],
                '-maxrate', tier['maxrate'],
                '-bufsize', tier['bufsize'],
                '-c:a', 'aac',
                '-b:a', tier['audio_bitrate'],
                '-hls_time', '6',
                '-hls_playlist_type', 'vod',
                '-hls_key_info_file', str(key_info_file.resolve()),
                '-hls_segment_filename', str((tier_dir / 'segment_%03d.ts').resolve()),
                str(tier_m3u8.resolve()),
            ]

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if tier_m3u8.exists():
                    generated_tiers.append({
                        'label': label,
                        'height': tier['height'],
                        'width': tier['width'],
                        'bandwidth': tier['bandwidth'],
                        'encoded': True,
                    })
                    master_lines.append(
                        f'#EXT-X-STREAM-INF:BANDWIDTH={tier["bandwidth"]},RESOLUTION={tier["width"]}x{tier["height"]},NAME="{label}"'
                    )
                    master_lines.append(f"{label}/index.m3u8")
            except Exception:
                pass
            finally:
                try:
                    os.remove(key_info_file)
                except OSError:
                    pass

        if generated_tiers:
            master_path = hls_dir / 'master.m3u8'
            with open(master_path, 'w', encoding='utf-8') as mf:
                mf.write('\n'.join(master_lines) + '\n')

            lesson.hls_playlist_relpath = f"hls/{lesson.id}/master.m3u8"
            lesson.video_qualities = generated_tiers
            lesson.transcode_status = 'ready'
            lesson.save(
                update_fields=[
                    'aes_key',
                    'aes_iv',
                    'hls_playlist_relpath',
                    'video_qualities',
                    'transcode_status',
                    'duration_seconds',
                ]
            )
            return lesson.hls_playlist_relpath

    # Safe protected direct stream fallback when ffmpeg is absent
    lesson.hls_playlist_relpath = ''
    lesson.video_qualities = [
        {
            'label': tier['label'],
            'height': tier['height'],
            'width': tier['width'],
            'bandwidth': tier['bandwidth'],
            'encoded': False,
        }
        for tier in QUALITY_TIERS
    ]
    lesson.transcode_status = 'stream_only'
    lesson.save(
        update_fields=[
            'aes_key',
            'aes_iv',
            'hls_playlist_relpath',
            'video_qualities',
            'transcode_status',
            'duration_seconds',
        ]
    )
    return None
