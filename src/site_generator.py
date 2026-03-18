"""Generate a static website from processed hearing transcripts."""

import json
import os
import shutil
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

import re

from src.transcriber import format_timestamp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "site", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "site", "static")
OUTPUT_DIR = os.path.join(BASE_DIR, "docs")  # GitHub Pages uses /docs
DATA_DIR = os.path.join(BASE_DIR, "data")
HEARINGS_DIR = os.path.join(DATA_DIR, "hearings")


def _is_noise_segment(text):
    """Check if a transcript segment is noise/hallucination."""
    text = text.strip().lower()
    if len(text) < 3:
        return True
    # Single repeated common words (Whisper hallucination on silence)
    noise_words = {'you', 'the', 'a', 'and', 'um', 'uh', 'oh', 'i', 'we', 'so', 'it'}
    if text in noise_words:
        return True
    # Repetitive patterns: same word 3+ times
    words = text.split()
    if len(words) >= 3 and len(set(words)) == 1:
        return True
    # Very short nonsense
    if len(words) <= 2 and all(w in noise_words for w in words):
        return True
    # Pre-hearing technical chatter (phone numbers, audio checks)
    if re.search(r'\d{7,}', text) and len(words) < 15:
        return True
    if re.search(r'\d{3,4}-\s*\d{0,7}', text) and len(words) < 20:
        return True
    if 'audio hot' in text:
        return True
    return False


def _remove_repeated_segments(segments):
    """Remove segments that repeat frequently (pre-hearing audio checks, loops)."""
    if not segments:
        return segments

    from collections import Counter
    # Count normalized text occurrences
    text_counts = Counter()
    for s in segments:
        normalized = s.get('text', '').strip().lower()
        if len(normalized) > 10:  # Only count substantive segments
            text_counts[normalized] += 1

    # Texts that appear 3+ times are likely noise/loops
    repeated_texts = {t for t, c in text_counts.items() if c >= 3}

    return [s for s in segments
            if s.get('text', '').strip().lower() not in repeated_texts]


def _consolidate_segments(segments, group_seconds=30):
    """Consolidate short segments into paragraphs grouped by time windows."""
    if not segments:
        return []

    # Filter noise first
    clean = [s for s in segments if not _is_noise_segment(s.get('text', ''))]
    # Remove repeated/looped segments (pre-hearing audio checks etc.)
    clean = _remove_repeated_segments(clean)
    if not clean:
        return []

    # Group into paragraphs by time windows
    paragraphs = []
    current_group = [clean[0]]

    for seg in clean[1:]:
        prev_end = current_group[-1].get('end', current_group[-1].get('start', 0))
        curr_start = seg.get('start', 0)
        # Start new paragraph if gap > group_seconds or group is getting long
        group_text = ' '.join(s['text'].strip() for s in current_group)
        if (curr_start - prev_end > group_seconds) or len(group_text.split()) > 150:
            paragraphs.append({
                'start': current_group[0].get('start', 0),
                'end': current_group[-1].get('end', current_group[-1].get('start', 0)),
                'text': group_text,
            })
            current_group = [seg]
        else:
            current_group.append(seg)

    # Don't forget the last group
    if current_group:
        group_text = ' '.join(s['text'].strip() for s in current_group)
        paragraphs.append({
            'start': current_group[0].get('start', 0),
            'end': current_group[-1].get('end', current_group[-1].get('start', 0)),
            'text': group_text,
        })

    return paragraphs


def load_all_hearings():
    """Load all processed hearing data."""
    hearings = []

    if not os.path.exists(HEARINGS_DIR):
        return hearings

    for entry in os.listdir(HEARINGS_DIR):
        hearing_dir = os.path.join(HEARINGS_DIR, entry)
        if not os.path.isdir(hearing_dir):
            continue

        info_path = os.path.join(hearing_dir, "info.json")
        transcript_path = os.path.join(hearing_dir, "transcript.json")
        summary_path = os.path.join(hearing_dir, "summary.json")

        if not os.path.exists(info_path) or not os.path.exists(transcript_path):
            continue

        with open(info_path) as f:
            info = json.load(f)
        with open(transcript_path) as f:
            transcript = json.load(f)

        summary = None
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)

        # Check for EPUB
        epub_path = None
        for fname in os.listdir(hearing_dir):
            if fname.endswith('.epub'):
                epub_path = fname
                break

        # Clean up field hearing location (address stored as JSON string)
        loc = info.get("location", {})
        if isinstance(loc, dict) and "address" in loc and not loc.get("building"):
            try:
                addr = json.loads(loc["address"])
                parts = []
                if addr.get("building_name"):
                    parts.append(addr["building_name"])
                if addr.get("street-address"):
                    parts.append(addr["street-address"])
                city_state = []
                if addr.get("city"):
                    city_state.append(addr["city"])
                if addr.get("state"):
                    city_state.append(addr["state"])
                if city_state:
                    parts.append(", ".join(city_state))
                if addr.get("postal_code"):
                    parts[-1] = parts[-1] + " " + addr["postal_code"]
                # Format as "Building Name, Street Address, City, State ZIP"
                info["location"] = ", ".join(parts)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        hearings.append({
            "info": info,
            "transcript": transcript,
            "summary": summary,
            "epub_filename": epub_path,
            "event_id": entry,
        })

    # Sort by date, most recent first
    hearings.sort(key=lambda h: h["info"].get("date", ""), reverse=True)
    return hearings


def generate_site(base_url="/committee-transcripts/"):
    """Generate the complete static site."""
    print("Generating static site...")

    hearings = load_all_hearings()
    print(f"  Found {len(hearings)} hearings with transcripts")

    if not hearings:
        print("  No hearings to generate site from!")
        return

    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    env.filters['format_timestamp'] = format_timestamp
    env.filters['slugify'] = _slugify
    def _format_date(d):
        if not d:
            return 'Unknown'
        try:
            dt = datetime.fromisoformat(d.replace('Z', '+00:00'))
            return dt.strftime('%B %-d, %Y')
        except (ValueError, AttributeError):
            return d[:10] if d else 'Unknown'
    env.filters['format_date'] = _format_date
    env.filters['truncate_words'] = lambda s, n=30: ' '.join(s.split()[:n]) + ('...' if len(s.split()) > n else '')
    env.filters['clean_title'] = _clean_title

    # Prepare output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Copy static files
    static_out = os.path.join(OUTPUT_DIR, "static")
    if os.path.exists(static_out):
        shutil.rmtree(static_out)
    if os.path.exists(STATIC_DIR):
        shutil.copytree(STATIC_DIR, static_out)

    # Build committee index
    committees = {}
    for h in hearings:
        hearing_chamber = h["info"].get("chamber", "")
        for c in h["info"].get("committees", []):
            name = c.get("name", "Unknown")
            # Inherit chamber from hearing if missing on committee
            chamber = c.get("chamber", "") or hearing_chamber
            if name not in committees:
                committees[name] = {
                    "name": name,
                    "chamber": chamber,
                    "hearings": [],
                }
            committees[name]["hearings"].append(h)

    # Common template variables
    common_vars = {
        "base_url": base_url,
        "generated_at": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    }

    # Generate index page
    template = env.get_template("index.html")
    html = template.render(
        hearings=hearings,
        committees=committees,
        total_hearings=len(hearings),
        **common_vars,
    )
    with open(os.path.join(OUTPUT_DIR, "index.html"), 'w') as f:
        f.write(html)
    print("  Generated: index.html")

    # Generate individual hearing pages
    hearing_template = env.get_template("hearing.html")
    hearings_out = os.path.join(OUTPUT_DIR, "hearings")
    os.makedirs(hearings_out, exist_ok=True)

    for h in hearings:
        event_id = h["event_id"]

        # Consolidate transcript segments into paragraphs
        raw_segments = h["transcript"].get("segments", [])
        consolidated = _consolidate_segments(raw_segments)
        display_transcript = dict(h["transcript"])
        display_transcript["paragraphs"] = consolidated

        html = hearing_template.render(
            hearing=h["info"],
            transcript=display_transcript,
            summary=h["summary"],
            epub_filename=h["epub_filename"],
            format_timestamp=format_timestamp,
            **common_vars,
        )

        hearing_page = os.path.join(hearings_out, f"{event_id}.html")
        with open(hearing_page, 'w') as f:
            f.write(html)

        # Copy EPUB to output
        if h["epub_filename"]:
            epub_src = os.path.join(HEARINGS_DIR, event_id, h["epub_filename"])
            epub_dst = os.path.join(hearings_out, h["epub_filename"])
            if os.path.exists(epub_src):
                shutil.copy2(epub_src, epub_dst)

    print(f"  Generated: {len(hearings)} hearing pages")

    # Generate committee pages
    committee_template = env.get_template("committee.html")
    committees_out = os.path.join(OUTPUT_DIR, "committees")
    os.makedirs(committees_out, exist_ok=True)

    for name, committee_data in committees.items():
        slug = _slugify(name)
        html = committee_template.render(
            committee=committee_data,
            format_timestamp=format_timestamp,
            **common_vars,
        )
        with open(os.path.join(committees_out, f"{slug}.html"), 'w') as f:
            f.write(html)

    print(f"  Generated: {len(committees)} committee pages")

    # Generate about page
    about_template = env.get_template("about.html")
    html = about_template.render(
        total_hearings=len(hearings),
        **common_vars,
    )
    with open(os.path.join(OUTPUT_DIR, "about.html"), 'w') as f:
        f.write(html)
    print("  Generated: about.html")

    # Generate RSS feed
    _generate_rss(hearings, base_url, OUTPUT_DIR)
    print("  Generated: feed.xml")

    print(f"\nSite generated at: {OUTPUT_DIR}")
    return OUTPUT_DIR


def _generate_rss(hearings, base_url, output_dir):
    """Generate an RSS feed of recent hearing transcripts."""
    site_url = "https://jeremyschlatter-intern.github.io/committee-transcripts/"
    items = []
    for h in hearings[:20]:  # Latest 20
        event_id = h["event_id"]
        info = h["info"]
        title = _clean_title(info.get("title", "Untitled")) or info.get("title", "Untitled")
        date = info.get("date", "")
        chamber = info.get("chamber", "")
        committees = ", ".join(c.get("name", "") for c in info.get("committees", []))
        link = f"{site_url}hearings/{event_id}.html"

        # Build description
        desc_parts = []
        if chamber:
            desc_parts.append(f"{chamber} hearing")
        if committees:
            desc_parts.append(f"Committee: {committees}")
        if h.get("summary", {}) and h["summary"].get("overview"):
            overview = h["summary"]["overview"]
            # Truncate overview
            words = overview.split()[:50]
            desc_parts.append(" ".join(words) + ("..." if len(overview.split()) > 50 else ""))

        description = ". ".join(desc_parts) if desc_parts else title

        # Format date for RSS (RFC 822)
        pub_date = ""
        if date:
            try:
                dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except (ValueError, AttributeError):
                pass

        # Escape XML
        title_xml = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        desc_xml = description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        item = f"""    <item>
      <title>{title_xml}</title>
      <link>{link}</link>
      <guid>{link}</guid>
      <description>{desc_xml}</description>
      {f'<pubDate>{pub_date}</pubDate>' if pub_date else ''}
    </item>"""
        items.append(item)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Committee Proceeding Transcripts</title>
    <link>{site_url}</link>
    <description>Free, AI-generated transcripts of congressional committee hearings</description>
    <language>en-us</language>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>"""

    with open(os.path.join(output_dir, "feed.xml"), 'w') as f:
        f.write(rss)


def _slugify(text):
    """Convert text to URL-friendly slug."""
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]


def _clean_title(title):
    """Clean up verbose Senate hearing title format for display."""
    if not title:
        return title
    # Normalize non-breaking spaces
    normalized = title.replace('\xa0', ' ')
    # Strip "Hearings to examine " prefix
    prefixes = [
        "Hearings to examine ",
        "Hearing to examine ",
        "Hearings to consider ",
        "Hearing to consider ",
    ]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            cleaned = normalized[len(prefix):]
            # Capitalize the first letter
            if cleaned:
                cleaned = cleaned[0].upper() + cleaned[1:]
            # Remove trailing period
            if cleaned.endswith('.'):
                cleaned = cleaned[:-1]
            return cleaned
    return title


if __name__ == "__main__":
    generate_site()
