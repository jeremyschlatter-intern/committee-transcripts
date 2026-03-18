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


def _is_procedural(sentence):
    """Check if a sentence is procedural/boilerplate rather than substantive."""
    s = sentence.lower()
    procedural_patterns = [
        r'\bcommittee\s+(will\s+)?come\s+to\s+order\b',
        r'\bunanimous\s+consent\b',
        r'\bwithout\s+objection\b',
        r'\bso\s+ordered\b',
        r'\bhearing\s+is\s+(now\s+)?adjourned\b',
        r'\byield\s+(back|my\s+time)\b',
        r'\brecognize[ds]?\s+(the\s+)?(gentleman|gentlewoman|gentlelady|member)\b',
        r'\bfive\s+(legislative\s+)?days?\b',
        r'\bsubmit\s+(additional\s+)?written\s+questions?\b',
        r'\bopening\s+statement\b',
        r'\bpledge\s+of\s+allegiance\b',
    ]
    for pattern in procedural_patterns:
        if re.search(pattern, s):
            return True
    return False


def _is_noise_text(text):
    """Check if text is mostly Whisper noise/hallucination."""
    text = text.strip().lower()
    if len(text) < 10:
        return True
    # Check for repetitive word patterns
    words = text.split()
    if len(words) >= 4:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.15:  # Less than 15% unique words = noise
            return True
    return False


def extractive_summary(transcript, num_sentences=10):
    """Create an extractive summary by picking substantive sentences.

    Filters out procedural language, noise, and repetitive content.
    Picks sentences that contain actual policy discussion or testimony.
    """
    text = transcript.get("text", "")
    if not text:
        return "No transcript text available."

    # Clean up common Whisper artifacts (dead air transcribed as noise)
    text = re.sub(r'^(\s*(you|the|and|a|um|uh|oh|I)\s*){3,}', '', text, flags=re.IGNORECASE)
    # Remove repetitive word sequences anywhere in text
    text = re.sub(r'(\b\w+\b)(\s+\1){4,}', r'\1', text)

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    # Filter out noise and repetitive sentences
    clean_sentences = []
    for s in sentences:
        if _is_noise_text(s):
            continue
        if _is_procedural(s):
            continue
        # Skip very short or very long sentences
        word_count = len(s.split())
        if word_count < 5 or word_count > 200:
            continue
        clean_sentences.append(s)

    if not clean_sentences:
        # Fallback to any non-noise sentences
        clean_sentences = [s for s in sentences if not _is_noise_text(s) and len(s.split()) > 5]

    if len(clean_sentences) <= num_sentences:
        return ' '.join(clean_sentences)

    # Score sentences by substantive content indicators
    scored = []
    for i, s in enumerate(clean_sentences):
        score = 0
        sl = s.lower()
        # Substantive topic keywords boost score
        topic_words = ['billion', 'million', 'percent', 'funding', 'budget', 'program',
                       'legislation', 'amendment', 'investigation', 'oversight', 'reform',
                       'security', 'policy', 'department', 'secretary', 'director',
                       'cost', 'infrastructure', 'military', 'education', 'health',
                       'housing', 'environment', 'energy', 'technology', 'court',
                       'report', 'found', 'evidence', 'concern', 'challenge', 'threat']
        for w in topic_words:
            if w in sl:
                score += 2
        # Longer sentences tend to be more substantive (up to a point)
        word_count = len(s.split())
        score += min(word_count / 10, 5)
        # Position: early and late sentences in testimony tend to be key points
        position = i / len(clean_sentences)
        if position < 0.15 or position > 0.85:
            score += 2
        scored.append((score, i, s))

    # Pick top-scoring sentences, preserving original order
    scored.sort(key=lambda x: x[0], reverse=True)
    top_indices = sorted([x[1] for x in scored[:num_sentences]])
    selected = [clean_sentences[i] for i in top_indices]

    return ' '.join(selected)


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
