"""Batch upgrade: re-transcribe hearings with base.en, regenerate summaries and EPUBs."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.transcriber import transcribe_audio, save_transcript, load_transcript
from src.summarizer import generate_summary
from src.epub_generator import create_hearing_epub

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hearings")


def upgrade_hearing(event_id, model_name="base.en"):
    """Re-transcribe a hearing with a better model and regenerate summary + EPUB."""
    hearing_dir = os.path.join(DATA_DIR, event_id)

    transcript_path = os.path.join(hearing_dir, "transcript.json")
    info_path = os.path.join(hearing_dir, "info.json")
    summary_path = os.path.join(hearing_dir, "summary.json")

    if not os.path.exists(transcript_path):
        print(f"  No transcript found for {event_id}")
        return False

    # Check current model
    with open(transcript_path) as f:
        transcript = json.load(f)

    current_source = transcript.get("source", "unknown")
    if "base" in current_source:
        print(f"  {event_id}: Already using {current_source}, skipping transcription")
    else:
        # Find the audio file
        audio_path = None
        for ext in ['.wav', '.m4a', '.mp3']:
            for fname in os.listdir(hearing_dir):
                if fname.endswith(ext):
                    audio_path = os.path.join(hearing_dir, fname)
                    break
            if audio_path:
                break

        if not audio_path:
            print(f"  {event_id}: No audio file found, skipping")
            return False

        # Re-transcribe
        print(f"  {event_id}: Re-transcribing with {model_name}...")
        start = time.time()
        transcript = transcribe_audio(audio_path, model_name=model_name.replace('.en', ''))
        elapsed = time.time() - start
        transcript["source"] = f"whisper_{model_name.replace('.', '')}"
        print(f"  {event_id}: Transcription completed in {elapsed:.0f}s ({len(transcript['segments'])} segments)")

        # Save new transcript
        save_transcript(transcript, transcript_path)

    # Reload transcript (in case we skipped transcription)
    with open(transcript_path) as f:
        transcript = json.load(f)

    # Load hearing info
    with open(info_path) as f:
        info = json.load(f)

    # Regenerate summary
    print(f"  {event_id}: Regenerating summary...")
    summary = generate_summary(transcript, info)
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Regenerate EPUB
    print(f"  {event_id}: Regenerating EPUB...")
    # Remove old EPUBs
    for fname in os.listdir(hearing_dir):
        if fname.endswith('.epub'):
            os.remove(os.path.join(hearing_dir, fname))

    epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
    create_hearing_epub(transcript, info, summary, epub_path)

    print(f"  {event_id}: Done!")
    return True


if __name__ == "__main__":
    # Find hearings that need upgrading
    needs_upgrade = []
    already_good = []

    for entry in os.listdir(DATA_DIR):
        hearing_dir = os.path.join(DATA_DIR, entry)
        if not os.path.isdir(hearing_dir):
            continue
        transcript_path = os.path.join(hearing_dir, "transcript.json")
        if not os.path.exists(transcript_path):
            continue
        with open(transcript_path) as f:
            t = json.load(f)
        source = t.get("source", "unknown")
        if "base" in source:
            already_good.append(entry)
        else:
            needs_upgrade.append(entry)

    print(f"Hearings already on base.en: {already_good}")
    print(f"Hearings needing upgrade: {needs_upgrade}")
    print()

    for event_id in needs_upgrade:
        upgrade_hearing(event_id)
        print()

    # Also regenerate summaries for already-good hearings
    for event_id in already_good:
        hearing_dir = os.path.join(DATA_DIR, event_id)
        transcript_path = os.path.join(hearing_dir, "transcript.json")
        info_path = os.path.join(hearing_dir, "info.json")
        summary_path = os.path.join(hearing_dir, "summary.json")

        with open(transcript_path) as f:
            transcript = json.load(f)
        with open(info_path) as f:
            info = json.load(f)

        print(f"  {event_id}: Regenerating summary...")
        summary = generate_summary(transcript, info)
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"  {event_id}: Regenerating EPUB...")
        for fname in os.listdir(hearing_dir):
            if fname.endswith('.epub'):
                os.remove(os.path.join(hearing_dir, fname))
        epub_path = os.path.join(hearing_dir, f"hearing_{event_id}.epub")
        create_hearing_epub(transcript, info, summary, epub_path)

    print("\nAll hearings upgraded!")
