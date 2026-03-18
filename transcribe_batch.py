"""Batch transcribe all downloaded hearings."""
import warnings
warnings.filterwarnings('ignore')

import json
import os
import sys
from src.congress_api import get_committee_meeting_detail, extract_meeting_info
from src.transcriber import transcribe_audio, save_transcript
from src.summarizer import generate_summary
from src.epub_generator import create_hearing_epub

HEARINGS = [
    {"event_id": 118923, "chamber": "house", "youtube_id": "vLHJJ_wjADU"},
    {"event_id": 119001, "chamber": "house", "youtube_id": "1Taz9trrkG4"},
    {"event_id": 118881, "chamber": "house", "youtube_id": "EdHfPqCTOgs"},
    {"event_id": 119032, "chamber": "house", "youtube_id": "d_Db7k5ig7k"},
]

MODEL = "tiny"  # Use tiny for speed; base for quality

for h in HEARINGS:
    eid = h["event_id"]
    hearing_dir = f"data/hearings/{eid}"
    os.makedirs(hearing_dir, exist_ok=True)

    transcript_path = f"{hearing_dir}/transcript.json"

    # Skip if already transcribed
    if os.path.exists(transcript_path):
        print(f"[{eid}] Already transcribed, skipping.")
        continue

    audio_path = f"data/audio/hearing_{eid}.wav"
    if not os.path.exists(audio_path):
        print(f"[{eid}] No audio file, skipping.")
        continue

    print(f"\n{'='*60}")
    print(f"[{eid}] Starting transcription...")

    # Get metadata
    try:
        detail = get_committee_meeting_detail(119, h["chamber"], eid)
        info = extract_meeting_info(detail)
        with open(f"{hearing_dir}/info.json", 'w') as f:
            json.dump(info, f, indent=2)
        print(f"  Title: {info['title'][:80]}")
    except Exception as e:
        print(f"  Warning: Could not get metadata: {e}")
        info = {"title": f"Hearing {eid}", "eventId": eid, "date": "", "chamber": h["chamber"], "committees": [], "witnesses": []}

    # Transcribe
    try:
        transcript = transcribe_audio(audio_path, model_name=MODEL)
        transcript["source"] = f"whisper_{MODEL}"
        save_transcript(transcript, transcript_path)
        print(f"  Transcribed: {len(transcript['segments'])} segments, {len(transcript['text'].split())} words")
    except Exception as e:
        print(f"  ERROR transcribing: {e}")
        continue

    # Summary
    summary = generate_summary(transcript, info)
    with open(f"{hearing_dir}/summary.json", 'w') as f:
        json.dump(summary, f, indent=2)

    # EPUB
    try:
        create_hearing_epub(transcript, info, summary, f"{hearing_dir}/hearing_{eid}.epub")
    except Exception as e:
        print(f"  EPUB error: {e}")

    print(f"[{eid}] Done!")

print("\n\nAll hearings processed!")
