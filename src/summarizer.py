"""Generate summaries of hearing transcripts."""

import json
import os
import re


def chunk_text(text, max_chars=4000):
    """Split text into chunks for processing."""
    words = text.split()
    chunks = []
    current = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > max_chars and current:
            chunks.append(' '.join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1

    if current:
        chunks.append(' '.join(current))

    return chunks


def extractive_summary(transcript, num_sentences=10):
    """Create a simple extractive summary by picking key sentences.

    This is a lightweight fallback that doesn't require an API.
    It picks sentences based on position (intro, conclusion) and length.
    """
    text = transcript.get("text", "")
    if not text:
        return "No transcript text available."

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) <= num_sentences:
        return ' '.join(sentences)

    # Pick: first 2, last 2, and longest from the middle
    selected = []
    selected.extend(sentences[:2])
    selected.extend(sentences[-2:])

    # From the middle, pick sentences by length (longer = more substantive)
    middle = sentences[2:-2]
    middle_sorted = sorted(middle, key=len, reverse=True)
    remaining = num_sentences - len(selected)
    # Pick the longest sentences from the middle, preserving original order
    middle_picks = set()
    for s in middle_sorted[:remaining]:
        middle_picks.add(middle.index(s))
    for idx in sorted(middle_picks):
        selected.insert(-2, middle[idx])

    return ' '.join(selected[:num_sentences])


def generate_summary(transcript, hearing_info=None):
    """Generate a summary for a hearing transcript.

    Uses extractive summarization as a reliable method.
    Returns a dict with summary sections.
    """
    text = transcript.get("text", "")
    segments = transcript.get("segments", [])

    # Basic statistics
    word_count = len(text.split())
    duration_seconds = segments[-1]["end"] if segments else 0
    duration_minutes = int(duration_seconds / 60)

    # Extract key overview
    overview = extractive_summary(transcript, num_sentences=6)

    # Build hearing context
    context = ""
    if hearing_info:
        context += f"**Committee**: {', '.join(c['name'] for c in hearing_info.get('committees', []))}\n\n"
        if hearing_info.get('witnesses'):
            context += "**Witnesses**:\n"
            for w in hearing_info['witnesses']:
                parts = [w.get('name', '')]
                if w.get('position'):
                    parts.append(w['position'])
                if w.get('organization'):
                    parts.append(w['organization'])
                context += f"- {', '.join(p for p in parts if p)}\n"
            context += "\n"

    return {
        "overview": overview,
        "context": context,
        "statistics": {
            "word_count": word_count,
            "duration_minutes": duration_minutes,
            "segment_count": len(segments),
        },
    }


def format_summary_markdown(summary, title=""):
    """Format a summary dict as markdown."""
    md = []

    if title:
        md.append(f"# Summary: {title}\n")

    if summary.get("context"):
        md.append(summary["context"])

    stats = summary.get("statistics", {})
    md.append(f"**Duration**: ~{stats.get('duration_minutes', 0)} minutes | "
              f"**Words**: {stats.get('word_count', 0):,}\n")

    if summary.get("overview"):
        md.append("## Key Points\n")
        md.append(summary["overview"])
        md.append("")

    return "\n".join(md)
