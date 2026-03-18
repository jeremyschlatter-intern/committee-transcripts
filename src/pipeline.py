"""Main pipeline: discover hearings, extract audio, transcribe, generate site."""

import json
import os
import sys
import time
from datetime import datetime

from src.congress_api import (
    discover_recent_hearings,
    get_recent_committee_meetings,
    get_committee_meeting_detail,
    extract_meeting_info,
)
from src.audio_extractor import (
    extract_congress_gov_video_id,
    download_audio_from_youtube,
    get_youtube_captions,
)
from src.transcriber import (
    transcribe_audio,
    parse_vtt_captions,
    save_transcript,
    load_transcript,
    format_transcript_text,
)
from src.summarizer import generate_summary, format_summary_markdown
from src.epub_generator import create_hearing_epub

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
HEARINGS_DIR = os.path.join(DATA_DIR, "hearings")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
TRANSCRIPTS_DIR = os.path.join(DATA_DIR, "transcripts")


def process_hearing(meeting_info, use_whisper=True, whisper_model="base"):
    """Process a single hearing: download audio, transcribe, summarize.

    Args:
        meeting_info: dict from congress_api.extract_meeting_info()
        use_whisper: if True, use Whisper for transcription; if False, use YouTube captions
        whisper_model: Whisper model size ('tiny', 'base', 'small', 'medium')

    Returns:
        dict with hearing_info, transcript, summary, paths
    """
    event_id = meeting_info.get("eventId", "unknown")
    hearing_dir = os.path.join(HEARINGS_DIR, str(event_id))
    os.makedirs(hearing_dir, exist_ok=True)

    # Save hearing metadata
    info_path = os.path.join(hearing_dir, "info.json")
    with open(info_path, 'w') as f:
        json.dump(meeting_info, f, indent=2)

    # Find video URL and extract YouTube ID
    video_id = None
    video_url = None
    for video in meeting_info.get("videos", []):
        url = video.get("url", "")
        vid = extract_congress_gov_video_id(url)
        if vid:
            video_id = vid
            video_url = url
            break

    if not video_id:
        print(f"  No YouTube video found for event {event_id}")
        return None

    print(f"\n{'='*60}")
    print(f"Processing: {meeting_info.get('title', 'Unknown')[:80]}")
    print(f"Event ID: {event_id} | YouTube: {video_id}")
    print(f"{'='*60}")

    # Check for existing transcript
    transcript_path = os.path.join(hearing_dir, "transcript.json")
    if os.path.exists(transcript_path):
        print("  Loading existing transcript...")
        transcript = load_transcript(transcript_path)
    else:
        # Try YouTube captions first (faster and free)
        transcript = None
        captions_path = get_youtube_captions(video_id, hearing_dir, f"captions_{event_id}")

        if captions_path and not use_whisper:
            print("  Using YouTube auto-captions...")
            transcript = parse_vtt_captions(captions_path)
            transcript["source"] = "youtube_captions"
        else:
            # Download audio and transcribe with Whisper
            try:
                audio_path = download_audio_from_youtube(
                    video_id, AUDIO_DIR, f"hearing_{event_id}"
                )
                if use_whisper:
                    print(f"  Transcribing with Whisper ({whisper_model})...")
                    transcript = transcribe_audio(audio_path, model_name=whisper_model)
                    transcript["source"] = f"whisper_{whisper_model}"
                elif captions_path:
                    transcript = parse_vtt_captions(captions_path)
                    transcript["source"] = "youtube_captions"
            except Exception as e:
                print(f"  Error extracting audio: {e}")
                # Fall back to captions if available
                if captions_path:
                    transcript = parse_vtt_captions(captions_path)
                    transcript["source"] = "youtube_captions"

        if transcript:
            save_transcript(transcript, transcript_path)

    if not transcript:
        print("  Failed to get transcript")
        return None

    # Generate summary
    summary = generate_summary(transcript, meeting_info)
    summary_path = os.path.join(hearing_dir, "summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    # Generate EPUB
    epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
    try:
        create_hearing_epub(transcript, meeting_info, summary, epub_path)
    except Exception as e:
        print(f"  EPUB generation error: {e}")
        epub_path = None

    return {
        "hearing_info": meeting_info,
        "transcript": transcript,
        "summary": summary,
        "paths": {
            "info": info_path,
            "transcript": transcript_path,
            "summary": summary_path,
            "epub": epub_path,
        },
    }


def run_pipeline(days_back=30, max_hearings=10, chamber=None,
                 use_whisper=True, whisper_model="base"):
    """Run the full pipeline: discover, transcribe, and generate site.

    Args:
        days_back: how many days back to look for hearings
        max_hearings: maximum number of hearings to process
        chamber: 'house', 'senate', or None for both
        use_whisper: use Whisper (True) or YouTube captions (False)
        whisper_model: Whisper model size

    Returns:
        list of processed hearing results
    """
    print(f"\n{'#'*60}")
    print(f"# Committee Proceeding Transcripts Pipeline")
    print(f"# Looking back {days_back} days, max {max_hearings} hearings")
    print(f"# Chamber: {chamber or 'both'}")
    print(f"# Transcription: {'Whisper (' + whisper_model + ')' if use_whisper else 'YouTube captions'}")
    print(f"{'#'*60}\n")

    # Discover hearings
    print("Discovering recent committee meetings with video...")
    chambers = [chamber] if chamber else ["house", "senate"]
    all_meetings = []

    for ch in chambers:
        meetings = discover_recent_hearings(days_back=days_back, chamber=ch)
        all_meetings.extend(meetings)
        print(f"  {ch.title()}: {len(meetings)} meetings with video")

    # Sort by date, most recent first
    all_meetings.sort(key=lambda m: m.get("date", ""), reverse=True)

    # Limit
    meetings_to_process = all_meetings[:max_hearings]
    print(f"\nProcessing {len(meetings_to_process)} of {len(all_meetings)} meetings...\n")

    # Process each
    results = []
    for i, meeting in enumerate(meetings_to_process):
        print(f"\n[{i+1}/{len(meetings_to_process)}]")
        try:
            result = process_hearing(
                meeting,
                use_whisper=use_whisper,
                whisper_model=whisper_model,
            )
            if result:
                results.append(result)
        except Exception as e:
            print(f"  Error processing hearing: {e}")

    print(f"\n{'#'*60}")
    print(f"# Pipeline complete: {len(results)} hearings processed")
    print(f"{'#'*60}\n")

    # Save manifest
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "hearings_processed": len(results),
        "hearings": [
            {
                "eventId": r["hearing_info"]["eventId"],
                "title": r["hearing_info"]["title"],
                "date": r["hearing_info"]["date"],
                "chamber": r["hearing_info"]["chamber"],
                "committees": [c["name"] for c in r["hearing_info"].get("committees", [])],
                "word_count": r["summary"]["statistics"]["word_count"],
                "duration_minutes": r["summary"]["statistics"]["duration_minutes"],
                "has_epub": r["paths"]["epub"] is not None,
            }
            for r in results
        ],
    }

    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest saved: {manifest_path}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process committee hearing transcripts")
    parser.add_argument("--days", type=int, default=30, help="Days to look back")
    parser.add_argument("--max", type=int, default=5, help="Max hearings to process")
    parser.add_argument("--chamber", choices=["house", "senate"], help="Filter by chamber")
    parser.add_argument("--captions-only", action="store_true", help="Use YouTube captions instead of Whisper")
    parser.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small", "medium"])

    args = parser.parse_args()

    results = run_pipeline(
        days_back=args.days,
        max_hearings=args.max,
        chamber=args.chamber,
        use_whisper=not args.captions_only,
        whisper_model=args.whisper_model,
    )
