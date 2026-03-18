"""Generate a static website from processed hearing transcripts."""

import json
import os
import shutil
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from src.transcriber import format_timestamp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "site", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "site", "static")
OUTPUT_DIR = os.path.join(BASE_DIR, "docs")  # GitHub Pages uses /docs
DATA_DIR = os.path.join(BASE_DIR, "data")
HEARINGS_DIR = os.path.join(DATA_DIR, "hearings")


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
    env.filters['format_date'] = lambda d: d[:10] if d else 'Unknown'
    env.filters['truncate_words'] = lambda s, n=30: ' '.join(s.split()[:n]) + ('...' if len(s.split()) > n else '')

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
        for c in h["info"].get("committees", []):
            name = c.get("name", "Unknown")
            if name not in committees:
                committees[name] = {
                    "name": name,
                    "chamber": c.get("chamber", ""),
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

        html = hearing_template.render(
            hearing=h["info"],
            transcript=h["transcript"],
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

    print(f"\nSite generated at: {OUTPUT_DIR}")
    return OUTPUT_DIR


def _slugify(text):
    """Convert text to URL-friendly slug."""
    import re
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]


if __name__ == "__main__":
    generate_site()
