"""Extract audio from committee hearing videos for transcription."""

import subprocess
import os
import re
import json
import shutil
import sys


def extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/.*[?&]v=([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_congress_gov_video_id(url):
    """Extract YouTube ID from congress.gov committee video URL.

    Congress.gov URLs like:
    https://www.congress.gov/committees/video/house-appropriations/hsap00/Z5DNOWdHzTU
    The last path segment is the YouTube video ID.
    """
    if "congress.gov/committees/video" in url:
        parts = url.rstrip("/").split("/")
        candidate = parts[-1]
        if re.match(r'^[a-zA-Z0-9_-]{11}$', candidate):
            return candidate
    return extract_youtube_id(url)


def download_audio_from_youtube(video_id, output_dir, filename=None):
    """Download audio from a YouTube video using yt-dlp.

    Returns path to the downloaded audio file.
    """
    if filename is None:
        filename = video_id

    output_path = os.path.join(output_dir, f"{filename}.wav")

    if os.path.exists(output_path):
        print(f"Audio already exists: {output_path}")
        return output_path

    os.makedirs(output_dir, exist_ok=True)

    url = f"https://www.youtube.com/watch?v={video_id}"

    # First download best audio
    temp_path = os.path.join(output_dir, f"{filename}.temp")

    # Find yt-dlp binary - prefer nix version (newer, handles SABR)
    yt_dlp_bin = shutil.which("yt-dlp")
    if not yt_dlp_bin:
        yt_dlp_cmd = [sys.executable, "-m", "yt_dlp"]
    else:
        yt_dlp_cmd = [yt_dlp_bin]

    # Try downloading audio-only format first (format 140 = m4a audio)
    temp_path = os.path.join(output_dir, f"{filename}.temp")

    cmd = yt_dlp_cmd + [
        "-f", "140/bestaudio",
        "-o", temp_path + ".%(ext)s",
        "--no-playlist",
        url,
    ]

    print(f"Downloading audio for {video_id}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)

    if result.returncode != 0:
        print(f"yt-dlp attempt 1 failed, trying format 18...")
        # Fallback to format 18 (360p mp4 with audio)
        cmd = yt_dlp_cmd + [
            "-f", "18",
            "-o", temp_path + ".mp4",
            "--no-playlist",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)

    if result.returncode != 0:
        print(f"yt-dlp error: {result.stderr[:500]}")
        raise RuntimeError(f"Failed to download audio: {result.stderr[:200]}")

    # Find the downloaded file and convert to 16kHz mono wav for Whisper
    for ext in ['.m4a', '.wav', '.webm', '.opus', '.mp3', '.mp4']:
        candidate = temp_path + ext
        if os.path.exists(candidate):
            convert_cmd = [
                "ffmpeg", "-i", candidate,
                "-vn",  # No video
                "-ar", "16000",  # 16kHz for Whisper
                "-ac", "1",  # mono
                "-y",
                output_path,
            ]
            subprocess.run(convert_cmd, capture_output=True, timeout=600)
            os.remove(candidate)
            break

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Audio saved: {output_path} ({size_mb:.1f} MB)")
        return output_path

    raise RuntimeError("Failed to produce audio file")


SENATE_STREAM_INFO = {
    "ag": {"id": "2036803", "msl3": "agriculture"},
    "aging": {"id": "2036801", "msl3": "aging"},
    "approps": {"id": "2036802", "msl3": "appropriations"},
    "armed": {"id": "2036800", "msl3": "armedservices"},
    "banking": {"id": "2036799", "msl3": "banking"},
    "budget": {"id": "2036798", "msl3": "budget"},
    "commerce": {"id": "2036779", "msl3": "commerce"},
    "energy": {"id": "2036797", "msl3": "energy"},
    "epw": {"id": "2036783", "msl3": "environment"},
    "ethics": {"id": "2036796", "msl3": "ethics"},
    "finance": {"id": "2036795", "msl3": "finance_finance"},
    "foreign": {"id": "2036794", "msl3": "foreignrelations"},
    "govtaff": {"id": "2036792", "msl3": "hsgac"},
    "help": {"id": "2036793", "msl3": "help"},
    "indian": {"id": "2036791", "msl3": "indianaffairs"},
    "intel": {"id": "2036790", "msl3": "intelligence"},
    "judiciary": {"id": "2036788", "msl3": "judiciary"},
    "rules": {"id": "2036787", "msl3": "rules"},
    "smbiz": {"id": "2036786", "msl3": "smallbusiness"},
    "vetaff": {"id": "2036785", "msl3": "veteransaffairs"},
}


def resolve_senate_isvp_url(isvp_url):
    """Convert a Senate ISVP URL to an HLS stream URL.

    Input:  https://www.senate.gov/isvp/?comm=help&filename=help031226
    Output: https://www-senate-gov-media-srs.akamaized.net/hls/live/{id}/{comm}/{filename}/master.m3u8
    """
    match = re.search(r'comm=(\w+).*filename=(\w+)', isvp_url)
    if not match:
        return None

    comm = match.group(1)
    filename = match.group(2)

    stream_info = SENATE_STREAM_INFO.get(comm)
    if not stream_info:
        return None

    stream_id = stream_info["id"]
    return f"https://www-senate-gov-media-srs.akamaized.net/hls/live/{stream_id}/{comm}/{filename}/master.m3u8"


def download_audio_from_hls(stream_url, output_dir, filename):
    """Download audio from an HLS stream (Senate Akamai).

    Returns path to the downloaded audio file.
    """
    output_path = os.path.join(output_dir, f"{filename}.wav")

    if os.path.exists(output_path):
        print(f"Audio already exists: {output_path}")
        return output_path

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-i", stream_url,
        "-vn",  # No video
        "-ar", "16000",
        "-ac", "1",
        "-y",
        output_path,
    ]

    print(f"Downloading audio from HLS stream...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[:200]}")

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Audio saved: {output_path} ({size_mb:.1f} MB)")
        return output_path

    raise RuntimeError("Failed to produce audio file")


def get_youtube_captions(video_id, output_dir, filename=None):
    """Try to get existing YouTube captions/subtitles.

    Returns path to subtitle file, or None if unavailable.
    """
    if filename is None:
        filename = video_id

    output_path = os.path.join(output_dir, f"{filename}.vtt")
    os.makedirs(output_dir, exist_ok=True)

    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "vtt",
        "--skip-download",
        "-o", os.path.join(output_dir, filename + ".%(ext)s"),
        "--no-playlist",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Look for the subtitle file
    for suffix in ['.en.vtt', '.vtt']:
        candidate = os.path.join(output_dir, filename + suffix)
        if os.path.exists(candidate):
            print(f"Found captions: {candidate}")
            return candidate

    return None


if __name__ == "__main__":
    # Test with a sample
    test_url = "https://www.congress.gov/committees/video/house-appropriations/hsap00/Z5DNOWdHzTU"
    vid = extract_congress_gov_video_id(test_url)
    print(f"Extracted YouTube ID: {vid}")
