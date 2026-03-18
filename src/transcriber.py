"""Transcribe audio using OpenAI Whisper."""

import os
import json
import whisper
import re


# Cache the model globally
_model = None


def get_model(model_name="base"):
    """Load Whisper model (cached)."""
    global _model
    if _model is None:
        print(f"Loading Whisper model '{model_name}'...")
        _model = whisper.load_model(model_name)
        print("Model loaded.")
    return _model


def transcribe_audio(audio_path, model_name="base", language="en"):
    """Transcribe an audio file using Whisper.

    Returns dict with:
    - text: full transcript text
    - segments: list of {start, end, text} dicts
    - language: detected language
    """
    model = get_model(model_name)

    print(f"Transcribing {audio_path}...")
    result = model.transcribe(
        audio_path,
        language=language,
        verbose=False,
        task="transcribe",
    )

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
        })

    return {
        "text": result["text"].strip(),
        "segments": segments,
        "language": result.get("language", language),
    }


def parse_vtt_captions(vtt_path):
    """Parse a VTT subtitle file into transcript segments.

    Returns dict with text and segments, similar to Whisper output.
    """
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove VTT header and metadata
    lines = content.split('\n')
    segments = []
    current_text = []
    current_start = None
    current_end = None
    seen_texts = set()  # Deduplicate

    time_pattern = re.compile(
        r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})'
    )

    for line in lines:
        line = line.strip()

        time_match = time_pattern.match(line)
        if time_match:
            # Save previous segment
            if current_text and current_start is not None:
                text = ' '.join(current_text)
                # Clean up YouTube auto-caption artifacts
                text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
                text = re.sub(r'\[.*?\]', '', text)  # Remove [Music] etc
                text = text.strip()
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    segments.append({
                        "start": current_start,
                        "end": current_end,
                        "text": text,
                    })

            # Parse new timing
            h1, m1, s1, ms1 = [int(x) for x in time_match.groups()[:4]]
            h2, m2, s2, ms2 = [int(x) for x in time_match.groups()[4:]]
            current_start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
            current_end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
            current_text = []
        elif line and not line.startswith('WEBVTT') and not line.startswith('Kind:') \
                and not line.startswith('Language:') and not re.match(r'^\d+$', line):
            # Clean the text
            cleaned = re.sub(r'<[^>]+>', '', line)
            if cleaned.strip():
                current_text.append(cleaned.strip())

    # Save last segment
    if current_text and current_start is not None:
        text = ' '.join(current_text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\[.*?\]', '', text)
        text = text.strip()
        if text and text not in seen_texts:
            segments.append({
                "start": current_start,
                "end": current_end,
                "text": text,
            })

    full_text = ' '.join(seg['text'] for seg in segments)

    return {
        "text": full_text,
        "segments": segments,
        "language": "en",
        "source": "youtube_captions",
    }


def format_timestamp(seconds):
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_transcript_text(transcript, include_timestamps=True):
    """Format transcript segments into readable text."""
    lines = []
    for seg in transcript.get("segments", []):
        if include_timestamps:
            ts = format_timestamp(seg["start"])
            lines.append(f"[{ts}] {seg['text']}")
        else:
            lines.append(seg["text"])

    return "\n".join(lines)


def save_transcript(transcript, output_path):
    """Save transcript as JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    print(f"Transcript saved: {output_path}")


def load_transcript(path):
    """Load a transcript JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
