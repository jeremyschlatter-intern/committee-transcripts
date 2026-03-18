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
        r'\bwritten\s+questions\s+(can|will|may)\s+be\s+submitted\b',
        r'\bopening\s+statement\b',
        r'\bpledge\s+of\s+allegiance\b',
        r'\bquestions\s+for\s+the\s+record\b',
        r'\bthank\s+(the\s+)?chairman\b',
        r'\bthank\s+(you\s+)?(ranking\s+member|chairman|mr\.\s+chairman)\b',
        r'\bauthored\s+or\s+edited\b',
        r'\bearned\s+(his|her)\s+(phd|ba|bs|jd|md)\b',
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


def extract_key_excerpts(transcript, num_excerpts=5, hearing_info=None):
    """Extract individual key excerpts with timestamps from transcript segments.

    Returns a list of dicts with 'text', 'start', 'end' for each excerpt.
    Unlike extractive_summary which returns a wall of text, this preserves
    structure for better display as individual blockquotes.
    """
    # Extract title keywords for relevance scoring
    title = hearing_info.get("title", "") if hearing_info else ""
    title_words = set(w.lower() for w in re.findall(r'\b\w{4,}\b', title))

    segments = transcript.get("segments", [])
    if not segments:
        return []

    # Build consolidated passages from segments (groups of ~30s)
    passages = []
    current_text = []
    current_start = segments[0].get("start", 0)
    current_end = 0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text or _is_noise_text(text):
            continue
        start = seg.get("start", 0)
        end = seg.get("end", start)

        if current_text and (start - current_end > 15 or len(" ".join(current_text).split()) > 80):
            passage = " ".join(current_text)
            if len(passage.split()) >= 15 and not _is_procedural(passage):
                passages.append({
                    "text": passage,
                    "start": current_start,
                    "end": current_end,
                })
            current_text = [text]
            current_start = start
        else:
            current_text.append(text)
        current_end = end

    # Don't forget last passage
    if current_text:
        passage = " ".join(current_text)
        if len(passage.split()) >= 15 and not _is_procedural(passage):
            passages.append({
                "text": passage,
                "start": current_start,
                "end": current_end,
            })

    if not passages:
        return []

    # Score passages
    scored = []
    for i, p in enumerate(passages):
        score = 0
        pl = p["text"].lower()
        words = p["text"].split()
        word_count = len(words)

        # Substantive keywords
        topic_words = ['billion', 'million', 'percent', 'funding', 'budget', 'program',
                       'legislation', 'amendment', 'investigation', 'oversight', 'reform',
                       'security', 'policy', 'department', 'secretary', 'director',
                       'cost', 'infrastructure', 'military', 'education', 'health',
                       'housing', 'environment', 'energy', 'technology', 'court',
                       'report', 'found', 'evidence', 'concern', 'challenge', 'threat',
                       'recommend', 'critical', 'important', 'significant']
        for w in topic_words:
            if w in pl:
                score += 2

        # Prefer medium-length passages (30-80 words)
        if 30 <= word_count <= 80:
            score += 5
        elif 15 <= word_count <= 30:
            score += 2

        # Penalize garbled text (sentences that don't end properly)
        if not p["text"].rstrip().endswith(('.', '!', '?', '"')):
            score -= 3

        # Penalize mid-sentence fragments (starts with lowercase or conjunction)
        first_word = p["text"].split()[0] if p["text"].split() else ""
        if first_word and first_word[0].islower():
            score -= 5
        if first_word.lower() in ('and', 'but', 'or', 'so', 'because', 'also', 'however'):
            score -= 4

        # Penalize if contains many short fragments or numbers without context
        if re.search(r'\d{5,}', pl):
            score -= 5

        # Penalize procedural content
        if _is_procedural(p["text"]):
            score -= 10

        # Penalize very early content (often procedural opening)
        if p["start"] < 60:
            score -= 3

        # Penalize "thank you" openings (transitions between speakers)
        if pl.startswith('thank you'):
            score -= 3

        # Reward relevance to hearing title
        title_matches = sum(1 for w in title_words if w in pl)
        score += title_matches * 2

        # Position diversity - spread excerpts across the hearing
        position = i / len(passages) if passages else 0
        p["_position"] = position

        scored.append((score, i, p))

    # Pick top-scoring, but ensure temporal spread
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    selected_positions = []
    for score, idx, passage in scored:
        if len(selected) >= num_excerpts:
            break
        # Ensure excerpts are spread across the hearing (at least 10% apart)
        pos = passage["_position"]
        if any(abs(pos - sp) < 0.1 for sp in selected_positions):
            continue
        # Clean up the passage text
        del passage["_position"]
        selected.append(passage)
        selected_positions.append(pos)

    # Sort by timestamp
    selected.sort(key=lambda x: x["start"])
    return selected


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

    # Extract structured key excerpts with timestamps
    key_excerpts = extract_key_excerpts(transcript, num_excerpts=5, hearing_info=hearing_info)

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

    # Pick the best excerpt for homepage display
    # Prefer one that starts with uppercase, reads as a complete thought,
    # and is relevant to the hearing title/topic
    title = hearing_info.get("title", "") if hearing_info else ""
    title_words = set(w.lower() for w in re.findall(r'\b\w{4,}\b', title))

    homepage_excerpt = ""
    if key_excerpts:
        best_score = -999
        for ex in key_excerpts:
            text = ex["text"].strip()
            if not text:
                continue
            score = 0
            first_char = text[0]
            first_word = text.split()[0].lower()

            # Must start with uppercase
            if not first_char.isupper():
                score -= 20
            # Penalize filler words
            if first_word in ('last', 'like', 'also', 'yeah', 'okay', 'well'):
                score -= 10
            # Penalize procedural
            if _is_procedural(text):
                score -= 20
            # Penalize thanking language
            tl = text.lower()
            if 'want to thank' in tl or 'thank chairman' in tl or 'thank the chairman' in tl:
                score -= 15
            # Penalize bio/credential introductions
            if 'authored or edited' in tl or 'earned his phd' in tl or 'earned her phd' in tl:
                score -= 15

            # Reward relevance to hearing title
            text_lower = text.lower()
            title_matches = sum(1 for w in title_words if w in text_lower)
            score += title_matches * 3

            # Reward substantive length
            word_count = len(text.split())
            if 20 <= word_count <= 60:
                score += 3

            if score > best_score:
                best_score = score
                homepage_excerpt = text

        if not homepage_excerpt:
            homepage_excerpt = key_excerpts[0]["text"]
        # Ensure first letter is capitalized
        if homepage_excerpt and homepage_excerpt[0].islower():
            homepage_excerpt = homepage_excerpt[0].upper() + homepage_excerpt[1:]

    return {
        "overview": overview,
        "homepage_excerpt": homepage_excerpt,
        "key_excerpts": key_excerpts,
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
