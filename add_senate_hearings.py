"""Add diverse Senate hearings via HLS streams (no YouTube bot issues)."""

import sys
import os
import json
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.congress_api import get_committee_meeting_detail, extract_meeting_info, enrich_hearing_info
from src.audio_extractor import resolve_senate_isvp_url, download_audio_from_hls
from src.transcriber import transcribe_audio, save_transcript
from src.summarizer import generate_summary
from src.epub_generator import create_hearing_epub

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hearings")


def process_senate_hearing(event_id, congress=119):
    """Process a Senate hearing end-to-end via ISVP HLS stream."""
    hearing_dir = os.path.join(DATA_DIR, str(event_id))
    os.makedirs(hearing_dir, exist_ok=True)

    info_path = os.path.join(hearing_dir, "info.json")
    transcript_path = os.path.join(hearing_dir, "transcript.json")
    summary_path = os.path.join(hearing_dir, "summary.json")

    # Skip if already done
    if os.path.exists(transcript_path):
        with open(transcript_path) as f:
            t = json.load(f)
        if "base" in t.get("source", ""):
            print(f"  {event_id}: Already has base.en transcript, skipping")
            return True

    # Get meeting info
    print(f"  {event_id}: Fetching meeting info...")
    try:
        detail = get_committee_meeting_detail(congress, "senate", event_id)
        info = extract_meeting_info(detail)
        info = enrich_hearing_info(info)
        with open(info_path, 'w') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  {event_id}: Failed to get info: {e}")
        return False

    print(f"  {event_id}: {info.get('title', '?')[:80]}")

    # Find ISVP video URL
    isvp_url = None
    for v in info.get("videos", []):
        url = v.get("url", "")
        if "senate.gov/isvp" in url:
            isvp_url = url
            break

    if not isvp_url:
        print(f"  {event_id}: No ISVP URL found")
        return False

    # Resolve to HLS URL
    hls_url = resolve_senate_isvp_url(isvp_url)
    if not hls_url:
        print(f"  {event_id}: Could not resolve ISVP URL")
        return False

    # Download audio
    try:
        audio_path = download_audio_from_hls(hls_url, hearing_dir, filename=str(event_id))
    except Exception as e:
        print(f"  {event_id}: HLS download failed: {e}")
        return False

    # Transcribe
    print(f"  {event_id}: Transcribing with Whisper base.en...")
    start = time.time()
    transcript = transcribe_audio(audio_path, model_name="base")
    elapsed = time.time() - start
    transcript["source"] = "whisper_base.en"
    print(f"  {event_id}: Transcribed in {elapsed:.0f}s ({len(transcript['segments'])} segments)")
    save_transcript(transcript, transcript_path)

    # Generate summary
    print(f"  {event_id}: Generating summary...")
    summary = generate_summary(transcript, info)
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Generate EPUB
    print(f"  {event_id}: Generating EPUB...")
    epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
    create_hearing_epub(transcript, info, summary, epub_path)

    # Clean up audio
    if os.path.exists(audio_path):
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        os.remove(audio_path)
        print(f"  {event_id}: Cleaned up audio ({size_mb:.0f}MB)")

    print(f"  {event_id}: DONE!")
    return True


# Senate hearings to add - diverse topics across many committees
SENATE_HEARINGS = [
    # Commerce - Section 230 / Platform Power (timely tech policy)
    "338063",
    # Judiciary - Big Tech and silencing Americans (free speech / tech)
    "337749",
    # Energy - Meeting electricity demand (energy policy)
    "337619",
    # Finance - Digital assets / taxation
    "337563",
    # Armed Services - Low-cost munitions (defense)
    "338080",
    # HELP - State of K-12 Education
    "337432",
    # Banking - Ensuring fair access to banking
    "337530",
    # Intelligence - Worldwide threats
    "338057",
]


if __name__ == "__main__":
    total = len(SENATE_HEARINGS)
    success = 0
    failed = []

    for i, event_id in enumerate(SENATE_HEARINGS, 1):
        print(f"\n[{i}/{total}] Processing Senate hearing {event_id}...")
        try:
            if process_senate_hearing(event_id):
                success += 1
            else:
                failed.append(event_id)
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(event_id)

    print(f"\n\nDone! {success}/{total} hearings processed successfully.")
    if failed:
        print(f"Failed: {failed}")
