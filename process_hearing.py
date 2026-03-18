"""Process a single hearing end-to-end: download, transcribe, summarize, generate EPUB."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.congress_api import get_committee_meeting_detail, extract_meeting_info, enrich_hearing_info
from src.audio_extractor import (
    extract_youtube_id, extract_congress_gov_video_id,
    download_audio_from_youtube, download_audio_from_hls, resolve_senate_isvp_url
)
from src.transcriber import transcribe_audio, save_transcript
from src.summarizer import generate_summary
from src.epub_generator import create_hearing_epub

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hearings")


def process_hearing(event_id, chamber, congress=119, model_name="base", force=False):
    """Process a hearing from API to published transcript.

    Args:
        event_id: Congress.gov event ID
        chamber: 'house' or 'senate'
        congress: Congress number (default 119)
        model_name: Whisper model name (default 'base' which uses base.en)
        force: If True, reprocess even if transcript exists
    """
    hearing_dir = os.path.join(DATA_DIR, str(event_id))
    os.makedirs(hearing_dir, exist_ok=True)

    info_path = os.path.join(hearing_dir, "info.json")
    transcript_path = os.path.join(hearing_dir, "transcript.json")
    summary_path = os.path.join(hearing_dir, "summary.json")

    # Check if already processed
    if os.path.exists(transcript_path) and not force:
        with open(transcript_path) as f:
            t = json.load(f)
        if "base" in t.get("source", ""):
            print(f"  {event_id}: Already has base.en transcript, skipping (use force=True to reprocess)")
            return True

    # Step 1: Get meeting info from API
    print(f"  {event_id}: Fetching meeting info...")
    try:
        detail = get_committee_meeting_detail(congress, chamber, event_id)
        info = extract_meeting_info(detail)
        info = enrich_hearing_info(info)
        with open(info_path, 'w') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
    except Exception as e:
        # If we already have info, use it
        if os.path.exists(info_path):
            with open(info_path) as f:
                info = json.load(f)
            print(f"  {event_id}: Using cached info (API error: {e})")
        else:
            print(f"  {event_id}: Failed to get info: {e}")
            return False

    print(f"  {event_id}: {info.get('title', '?')[:80]}")

    # Step 2: Download audio
    audio_path = None
    videos = info.get("videos", [])

    for v in videos:
        url = v.get("url", "")

        # Try YouTube
        yt_id = extract_congress_gov_video_id(url) or extract_youtube_id(url)
        if yt_id:
            try:
                audio_path = download_audio_from_youtube(yt_id, hearing_dir, filename=str(event_id))
                break
            except Exception as e:
                print(f"  {event_id}: YouTube download failed: {e}")
                continue

        # Try Senate ISVP
        if 'senate.gov/isvp' in url:
            hls_url = resolve_senate_isvp_url(url)
            if hls_url:
                try:
                    audio_path = download_audio_from_hls(hls_url, hearing_dir, filename=str(event_id))
                    break
                except Exception as e:
                    print(f"  {event_id}: Senate HLS download failed: {e}")
                    continue

    if not audio_path:
        # Check if audio already exists from previous download
        for fname in os.listdir(hearing_dir):
            if fname.endswith('.wav'):
                audio_path = os.path.join(hearing_dir, fname)
                break

    if not audio_path:
        print(f"  {event_id}: No audio available")
        return False

    # Step 3: Transcribe
    print(f"  {event_id}: Transcribing with Whisper {model_name}...")
    start = time.time()
    transcript = transcribe_audio(audio_path, model_name=model_name)
    elapsed = time.time() - start
    transcript["source"] = f"whisper_{model_name.replace('.', '')}en" if 'en' not in model_name else f"whisper_{model_name.replace('.', '')}"
    # Normalize source name
    if transcript["source"] == "whisper_baseen":
        transcript["source"] = "whisper_base.en"
    print(f"  {event_id}: Transcribed in {elapsed:.0f}s ({len(transcript['segments'])} segments, {len(transcript['text'].split())} words)")

    save_transcript(transcript, transcript_path)

    # Step 4: Generate summary
    print(f"  {event_id}: Generating summary...")
    summary = generate_summary(transcript, info)
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Step 5: Generate EPUB
    print(f"  {event_id}: Generating EPUB...")
    epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
    create_hearing_epub(transcript, info, summary, epub_path)

    # Clean up audio to save disk space
    if audio_path and os.path.exists(audio_path):
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        os.remove(audio_path)
        print(f"  {event_id}: Cleaned up audio ({size_mb:.0f}MB)")

    print(f"  {event_id}: DONE!")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python process_hearing.py <event_id> <chamber> [--force]")
        sys.exit(1)

    event_id = sys.argv[1]
    chamber = sys.argv[2]
    force = "--force" in sys.argv

    success = process_hearing(event_id, chamber, force=force)
    sys.exit(0 if success else 1)
