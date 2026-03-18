"""Add carefully selected Senate hearings with verified event IDs."""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.congress_api import get_committee_meeting_detail, extract_meeting_info, enrich_hearing_info
from src.audio_extractor import resolve_senate_isvp_url, download_audio_from_hls
from src.transcriber import transcribe_audio, save_transcript, get_model
from src.summarizer import generate_summary
from src.epub_generator import create_hearing_epub

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hearings")

# Pre-load model once
print("Pre-loading Whisper model...")
get_model("base")


def process_one(event_id):
    hearing_dir = os.path.join(DATA_DIR, str(event_id))
    os.makedirs(hearing_dir, exist_ok=True)
    info_path = os.path.join(hearing_dir, "info.json")
    transcript_path = os.path.join(hearing_dir, "transcript.json")
    summary_path = os.path.join(hearing_dir, "summary.json")

    if os.path.exists(transcript_path):
        with open(transcript_path) as f:
            t = json.load(f)
        if "base" in t.get("source", ""):
            print(f"  Already done, skipping")
            return True

    # Get info
    detail = get_committee_meeting_detail(119, "senate", event_id)
    info = extract_meeting_info(detail)
    info = enrich_hearing_info(info)
    with open(info_path, 'w') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(f"  Title: {info.get('title', '?')[:80]}")

    # Find ISVP URL
    isvp_url = None
    for v in info.get("videos", []):
        if "senate.gov/isvp" in v.get("url", ""):
            isvp_url = v["url"]
            break
    if not isvp_url:
        print(f"  No ISVP URL")
        return False

    hls_url = resolve_senate_isvp_url(isvp_url)
    if not hls_url:
        print(f"  Could not resolve ISVP")
        return False

    # Download
    audio_path = download_audio_from_hls(hls_url, hearing_dir, str(event_id))

    # Transcribe
    start = time.time()
    transcript = transcribe_audio(audio_path, model_name="base")
    elapsed = time.time() - start
    transcript["source"] = "whisper_base.en"
    print(f"  Transcribed in {elapsed:.0f}s ({len(transcript['segments'])} segments)")
    save_transcript(transcript, transcript_path)

    # Summary
    summary = generate_summary(transcript, info)
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # EPUB
    epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
    create_hearing_epub(transcript, info, summary, epub_path)

    # Cleanup
    os.remove(audio_path)
    return True


# Carefully picked hearings - diverse topics, different committees, from discovery API output
HEARINGS = [
    # AI copyright (Judiciary) - July 2025
    ("337253", "AI industry's mass ingestion of copyrighted works"),
    # AI in healthcare (HELP) - October 2025
    ("337474", "AI's potential to support patients, workers, children"),
    # Big Tech (Commerce) - October 2025
    ("337500", "Big Tech and silencing Americans"),
    # Digital assets (Banking) - July 2025
    ("337228", "From Wall Street to Web3: digital asset markets"),
    # K-12 Education (HELP) - September 2025
    ("337435", "State of K-12 education"),
    # Winning AI race (Commerce) - May 2025
    ("336923", "Winning the AI race: strengthening US capabilities"),
    # 23andMe privacy (Judiciary) - June 2025
    ("337055", "Privacy implications of 23andMe bankruptcy"),
]

if __name__ == "__main__":
    # Also remove the mis-identified business meeting
    bad_dir = os.path.join(DATA_DIR, "337432")
    if os.path.exists(bad_dir):
        import shutil
        shutil.rmtree(bad_dir)
        print("Removed mis-identified business meeting 337432\n")

    total = len(HEARINGS)
    success = 0
    for i, (eid, desc) in enumerate(HEARINGS, 1):
        print(f"\n[{i}/{total}] {eid}: {desc}")
        try:
            if process_one(eid):
                success += 1
        except Exception as e:
            print(f"  FAILED: {e}")

    print(f"\n\nDone: {success}/{total} succeeded")
