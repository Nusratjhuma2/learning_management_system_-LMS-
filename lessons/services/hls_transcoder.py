import os
import secrets
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding


def get_private_media_root():
    return getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')


def generate_aes_key():
    return secrets.token_bytes(16)


def generate_aes_iv():
    return secrets.token_hex(16)


def transcode_lesson_video(lesson):
    """
    Transcode and encrypt a lesson's raw_video into HLS (AES-128 encrypted).
    Uses ffmpeg if available on PATH; otherwise provides a pure-Python
    encrypted chunk-stream fallback.
    """
    if not lesson.raw_video:
        return None

    private_root = Path(get_private_media_root())
    raw_path = Path(lesson.raw_video.path)
    if not raw_path.exists():
        return None

    # Generate or reuse 16-byte AES-128 key and 16-byte hex IV
    if not lesson.aes_key:
        lesson.aes_key = secrets.token_bytes(16)
    if not lesson.aes_iv:
        lesson.aes_iv = secrets.token_hex(16)

    hls_dir = private_root / 'hls' / str(lesson.id)
    hls_dir.mkdir(parents=True, exist_ok=True)
    m3u8_file = hls_dir / 'index.m3u8'
    key_file = hls_dir / 'key.bin'

    with open(key_file, 'wb') as f:
        f.write(lesson.aes_key)

    ffmpeg_bin = shutil.which('ffmpeg')
    if ffmpeg_bin:
        key_info_file = hls_dir / 'key_info.txt'
        with open(key_info_file, 'w') as f:
            f.write(f"key.bin\n{key_file.resolve()}\n{lesson.aes_iv}\n")

        cmd = [
            ffmpeg_bin, '-y', '-i', str(raw_path.resolve()),
            '-c:v', 'h264', '-c:a', 'aac',
            '-hls_time', '6',
            '-hls_playlist_type', 'vod',
            '-hls_key_info_file', str(key_info_file.resolve()),
            '-hls_segment_filename', str((hls_dir / 'segment_%03d.ts').resolve()),
            str(m3u8_file.resolve())
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            lesson.hls_playlist_relpath = f"hls/{lesson.id}/index.m3u8"
            lesson.save(update_fields=['aes_key', 'aes_iv', 'hls_playlist_relpath'])
            try:
                os.remove(key_info_file)
            except OSError:
                pass
            return lesson.hls_playlist_relpath
        except Exception:
            pass

    # Pure-Python Encrypted Chunk-Stream Fallback
    chunk_size = 512 * 1024  # 512 KB per chunk
    iv_bytes = bytes.fromhex(lesson.aes_iv)

    with open(raw_path, 'rb') as rf:
        raw_data = rf.read()

    total_len = len(raw_data)
    segments = []
    offset = 0
    seg_idx = 0

    while offset < total_len:
        chunk = raw_data[offset:offset + chunk_size]
        offset += chunk_size

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(chunk) + padder.finalize()

        cipher = Cipher(algorithms.AES(lesson.aes_key), modes.CBC(iv_bytes))
        encryptor = cipher.encryptor()
        encrypted_chunk = encryptor.update(padded_data) + encryptor.finalize()

        seg_name = f"segment_{seg_idx:03d}.ts"
        seg_file = hls_dir / seg_name
        with open(seg_file, 'wb') as sf:
            sf.write(encrypted_chunk)

        segments.append(seg_name)
        seg_idx += 1

    # Approximate 6s duration per chunk if total duration unknown
    est_duration = max(len(segments) * 6, lesson.duration_seconds or 60)
    seg_duration = round(est_duration / max(len(segments), 1), 2)

    with open(m3u8_file, 'w', encoding='utf-8') as mf:
        mf.write("#EXTM3U\n")
        mf.write("#EXT-X-VERSION:3\n")
        mf.write(f"#EXT-X-TARGETDURATION:{int(seg_duration) + 1}\n")
        mf.write("#EXT-X-MEDIA-SEQUENCE:0\n")
        mf.write("#EXT-X-PLAYLIST-TYPE:VOD\n")
        mf.write(f'#EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x{lesson.aes_iv}\n')
        for seg in segments:
            mf.write(f"#EXTINF:{seg_duration},\n")
            mf.write(f"{seg}\n")
        mf.write("#EXT-X-ENDLIST\n")

    if not lesson.duration_seconds:
        lesson.duration_seconds = est_duration

    lesson.hls_playlist_relpath = f"hls/{lesson.id}/index.m3u8"
    lesson.save(update_fields=['aes_key', 'aes_iv', 'hls_playlist_relpath', 'duration_seconds'])
    return lesson.hls_playlist_relpath
