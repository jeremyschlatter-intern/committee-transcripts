"""Generate EPUB files from hearing transcripts."""

import os
from ebooklib import epub
from src.transcriber import format_timestamp


def create_hearing_epub(transcript, hearing_info, summary, output_path):
    """Create an EPUB file for a hearing transcript.

    Args:
        transcript: dict with text, segments
        hearing_info: dict with title, date, committees, witnesses, etc.
        summary: dict from summarizer
        output_path: where to save the EPUB
    """
    book = epub.EpubBook()

    title = hearing_info.get("title", "Committee Hearing Transcript")
    date = hearing_info.get("date", "")
    committees = hearing_info.get("committees", [])
    committee_names = ", ".join(c["name"] for c in committees) if committees else "Unknown Committee"

    # Metadata
    book.set_identifier(f"hearing-{hearing_info.get('eventId', 'unknown')}")
    book.set_title(title)
    book.set_language("en")
    book.add_author("Committee Proceeding Transcripts (Auto-generated)")

    # CSS
    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content="""
body { font-family: Georgia, serif; line-height: 1.6; margin: 1em; }
h1 { font-size: 1.4em; color: #1a365d; border-bottom: 2px solid #2c5282; padding-bottom: 0.3em; }
h2 { font-size: 1.2em; color: #2c5282; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 1em; }
.timestamp { color: #718096; font-size: 0.85em; font-family: monospace; }
.segment { margin-bottom: 0.5em; }
.summary { background: #f7fafc; border-left: 3px solid #2c5282; padding: 0.5em 1em; margin: 1em 0; }
.witness-list { margin: 0.5em 0; }
.witness-list li { margin-bottom: 0.3em; }
""".encode('utf-8')
    )
    book.add_item(style)

    # Title page
    title_html = f"""
<html><head><link rel="stylesheet" href="style/default.css"/></head>
<body>
<h1>{_escape(title)}</h1>
<div class="meta">
<p><strong>Committee:</strong> {_escape(committee_names)}</p>
<p><strong>Date:</strong> {_escape(date[:10] if date else 'Unknown')}</p>
<p><strong>Chamber:</strong> {_escape(hearing_info.get('chamber', 'Unknown'))}</p>
</div>
"""

    witnesses = hearing_info.get("witnesses", [])
    if witnesses:
        title_html += '<h2>Witnesses</h2><ul class="witness-list">'
        for w in witnesses:
            parts = [w.get("name", "")]
            if w.get("position"):
                parts.append(w["position"])
            if w.get("organization"):
                parts.append(w["organization"])
            title_html += f"<li>{_escape(', '.join(p for p in parts if p))}</li>"
        title_html += "</ul>"

    title_html += """
<p class="meta"><em>Auto-generated transcript. May contain errors.</em></p>
</body></html>
"""
    title_chapter = epub.EpubHtml(title="Title", file_name="title.xhtml")
    title_chapter.set_content(title_html)
    title_chapter.add_item(style)
    book.add_item(title_chapter)

    # Summary chapter
    stats = summary.get("statistics", {})
    summary_html = f"""
<html><head><link rel="stylesheet" href="style/default.css"/></head>
<body>
<h1>Summary</h1>
<div class="meta">
<p><strong>Duration:</strong> ~{stats.get('duration_minutes', 0)} minutes |
<strong>Words:</strong> {stats.get('word_count', 0):,}</p>
</div>
<div class="summary">
<p>{_escape(summary.get('overview', 'No summary available.'))}</p>
</div>
</body></html>
"""
    summary_chapter = epub.EpubHtml(title="Summary", file_name="summary.xhtml")
    summary_chapter.set_content(summary_html)
    summary_chapter.add_item(style)
    book.add_item(summary_chapter)

    # Transcript chapter(s) - split long transcripts
    segments = transcript.get("segments", [])
    chunk_size = 500  # segments per chapter

    chapters = []
    for i in range(0, max(len(segments), 1), chunk_size):
        chunk = segments[i:i + chunk_size]
        chapter_num = i // chunk_size + 1
        total_chapters = (len(segments) - 1) // chunk_size + 1 if segments else 1

        if total_chapters > 1:
            chapter_title = f"Transcript (Part {chapter_num})"
        else:
            chapter_title = "Full Transcript"

        html = f'<html><head><link rel="stylesheet" href="style/default.css"/></head><body>\n'
        html += f"<h1>{chapter_title}</h1>\n"

        if chunk:
            for seg in chunk:
                ts = format_timestamp(seg["start"])
                html += f'<div class="segment"><span class="timestamp">[{ts}]</span> {_escape(seg["text"])}</div>\n'
        else:
            html += "<p>No transcript segments available.</p>\n"

        html += "</body></html>"

        ch = epub.EpubHtml(
            title=chapter_title,
            file_name=f"transcript_{chapter_num}.xhtml"
        )
        ch.set_content(html)
        ch.add_item(style)
        book.add_item(ch)
        chapters.append(ch)

    # Table of contents
    book.toc = [title_chapter, summary_chapter] + chapters

    # Navigation
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Spine
    book.spine = ['nav', title_chapter, summary_chapter] + chapters

    # Write
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    epub.write_epub(output_path, book)
    print(f"EPUB saved: {output_path}")
    return output_path


def _escape(text):
    """HTML-escape text."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))
