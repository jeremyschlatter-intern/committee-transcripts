# After-Action Report: Committee Proceeding Transcripts

**Project**: AI-Generated Transcripts of Congressional Committee Hearings
**Live Site**: https://jeremyschlatter-intern.github.io/committee-transcripts/
**Repository**: https://github.com/jeremyschlatter-intern/committee-transcripts
**Date**: March 17, 2026

---

## Executive Summary

I built a complete end-to-end system that automatically generates transcripts of congressional committee hearings from video streams and publishes them on a free, searchable website. The system currently covers **13 hearings** across **8 committees** from both the House and Senate, representing approximately **36 hours of audio** and **294,000 words** of transcribed text.

The entire project—from initial research to deployed website—was completed autonomously, including: API integration with Congress.gov, audio extraction from Senate HLS streams, speech-to-text transcription, extractive summarization, EPUB generation, static site generation, and GitHub Pages deployment.

---

## The Problem Solved

Official committee hearing transcripts can take a year or more to be published by the Government Publishing Office. Private transcription services charge fees that put public information behind paywalls. This creates a transparency gap where, by the time official transcripts are available, the policy discussions they document are no longer timely.

This project demonstrates that AI can close this gap, generating usable transcripts within hours of a hearing and publishing them for free.

---

## What I Built

### Pipeline Architecture

The system consists of seven Python modules forming an automated pipeline:

1. **`congress_api.py`** — Queries the Congress.gov API v3 for hearing metadata: committees, dates, witness lists, video URLs, and related documents. Handles pagination and rate limiting with exponential backoff.

2. **`audio_extractor.py`** — Extracts audio from hearing video sources. For Senate hearings, this resolves ISVP (Internet Streaming Video Player) URLs to HLS (HTTP Live Streaming) endpoints on Akamai CDN, then uses ffmpeg to download and convert to 16kHz mono WAV. For House hearings, it supports YouTube extraction (though YouTube's bot detection makes this unreliable).

3. **`transcriber.py`** — Transcribes audio using OpenAI's Whisper speech recognition model (base.en). Produces timestamped segments with start/end times for each phrase.

4. **`summarizer.py`** — Generates extractive summaries by scoring transcript segments for substantive content and filtering out procedural language (parliamentary phrases, roll calls, recesses). Produces an overview paragraph and key statistics.

5. **`epub_generator.py`** — Creates downloadable EPUB e-books of each hearing transcript, structured with metadata, chapters, and timestamps for offline reading.

6. **`site_generator.py`** — Generates a complete static website from Jinja2 templates. Includes an index page, individual hearing pages, committee pages, an about page, and an RSS feed. Handles segment consolidation (grouping short Whisper segments into readable paragraphs), noise filtering, and title cleanup.

7. **`pipeline.py`** — Orchestrates the full pipeline from discovery to publication.

### Website Features

- **Homepage** with hearing counts, search/filter, and a chronological hearing list
- **Hearing pages** with timestamps, video links, witness lists, key excerpts, related documents, transcript search, and "Copy Transcript" functionality
- **Committee pages** grouping hearings by committee
- **RSS feed** for subscription to new transcripts
- **EPUB downloads** for every hearing
- **Clickable timestamps** that link to the corresponding point in the source video
- **Responsive design** suitable for desktop and mobile

### Coverage

| Chamber | Committee | Hearings |
|---------|-----------|----------|
| House | Judiciary | 3 |
| House | Armed Services (Readiness) | 1 |
| House | Financial Services (Oversight) | 1 |
| Senate | Judiciary | 2 |
| Senate | Commerce, Science, and Transportation | 2 |
| Senate | Health, Education, Labor, and Pensions | 3 |
| Senate | Banking, Housing, and Urban Affairs | 1 |
| Senate | Judiciary (Crime Subcommittee) | 1 |

Topics range from AI copyright and healthcare to homeland security oversight, housing authority failures, and K-12 education.

---

## Process and Obstacles

### 1. Discovering Hearing Video Sources

**Challenge**: The Congress.gov API provides metadata about hearings but the video URL formats vary significantly between chambers and committees.

**What I tried**: Initially explored YouTube for House hearings and found it worked for downloading audio. However, YouTube's bot detection became increasingly aggressive, blocking automated downloads unpredictably.

**Resolution**: I shifted focus to Senate hearings, which use a more reliable system. Senate committees host video through an Internet Streaming Video Player (ISVP) that serves HLS streams via Akamai CDN. I reverse-engineered the URL pattern by examining the ISVP embed pages: each committee has a short code (e.g., `judiciary`, `commerce`, `armed`) and videos are identified by committee code + date (e.g., `judiciary031026`). The HLS master playlist URL follows a predictable pattern on `www-senate-gov-media-srs.akamaized.net`.

**Key insight**: Senate HLS streams are served as public CDN content without authentication, making them far more reliable than YouTube for automated processing.

### 2. Congress.gov API Rate Limiting

**Challenge**: The Congress.gov API has aggressive rate limiting (HTTP 429 responses) that would kill batch processing jobs partway through.

**What I tried**: Initially processed hearings sequentially with no delay, which worked for small batches but failed when processing more than 3-4 hearings at once.

**Resolution**: Implemented exponential backoff retry logic (30s, 60s, 90s waits on 429 responses) and added 15-second delays between hearing processing runs. This made batch processing reliable, allowing me to successfully process 5 hearings in a single batch run.

### 3. Whisper Hallucinations on Silence

**Challenge**: Whisper's base.en model generates repetitive hallucinated text (e.g., "you you you you you...") when processing silence or very quiet audio, which is common at the beginning and end of hearing streams.

**Resolution**: Implemented a multi-layer noise filter in the site generator:
- Segments shorter than 3 characters are removed
- Single repeated common words ("you", "the", "um") are removed
- Segments where the same word repeats 3+ times are removed
- Very short segments consisting only of noise words are removed

This filtering happens during paragraph consolidation, so the raw transcript data is preserved but the displayed version is clean.

### 4. Non-Breaking Spaces in Congress.gov Data

**Challenge**: Senate hearing titles from the Congress.gov API contain non-breaking space characters (`\xa0`) instead of regular spaces. This caused the title cleanup filter (which strips "Hearings to examine " prefixes) to silently fail, leaving verbose titles on the site.

**Discovery**: This was caught during a review cycle when I noticed Senate hearing titles still had the full "Hearings to examine..." prefix despite having written code to strip it.

**Resolution**: Added `title.replace('\xa0', ' ')` normalization before prefix matching. A small fix, but one that required understanding the exact character encoding of the API's response data.

### 5. Committee Slug Mismatch

**Challenge**: Committee page links on the index page were broken for all Senate committees. Clicking a committee link returned a 404 error.

**Root cause**: The Jinja template used `name | lower | replace(' ', '-')` to generate slugs, while the Python site generator used `re.sub(r'[^a-z0-9\s-]', '', slug)`. These produced different results for names containing commas (e.g., "Senate Commerce, Science, and Transportation" → the template kept commas, Python stripped them).

**Resolution**: Registered the Python `_slugify()` function as a Jinja filter so templates and generator use exactly the same logic. This immediately fixed all committee page links.

### 6. Field Hearing Location Data

**Challenge**: One hearing (Little Rock Housing Authority, event 119032) was a field hearing, and its location data in the API was structured differently from Capitol Hill hearings. Instead of `{"room": "2154", "building": "Rayburn"}`, it had an `address` field containing a JSON string inside the JSON object—a nested encoding that rendered as raw JSON on the page.

**Resolution**: Added parsing logic to detect this pattern, parse the nested JSON, and format it as a readable address: "Central Arkansas Library System (CALS), 100 Rock Street, Little Rock, AR 72202".

### 7. Large File in Git History

**Challenge**: A 100MB WAV file from hearing processing was accidentally committed to git. Even after deleting the file, git push failed because the file remained in history.

**Resolution**: Used `git filter-branch` to rewrite history and remove the WAV file from all commits, followed by a force push. Also ensured the pipeline consistently deletes WAV files after transcription to prevent recurrence.

### 8. Video Availability Timing

**Challenge**: Attempted to add recent hearings from the current week, but the Senate ISVP streams returned HTTP 404—the archived video wasn't yet available.

**What I learned**: Senate hearing videos appear to take several days to a week to be archived on the Akamai CDN after the hearing occurs. The ISVP URL is published in the API immediately, but the actual video content becomes available later. A production system would need to handle this with periodic retry logic.

---

## Iterative Improvement with DC Agent

Per the project instructions, I created a DC agent teammate (adopting the persona of Daniel Schuman, a government transparency advocate) to provide iterative feedback on the solution. The agent reviewed the site multiple times:

**Review Cycle 1-2** (earlier session): Identified fundamental issues with transcript quality (tiny model), missing Senate coverage, and basic UI problems. Led to upgrading all transcripts to Whisper base.en and adding Senate hearing support.

**Review Cycle 3**: Identified critical bugs—committee slug mismatches breaking all Senate committee links, misleading "Summary" labeling, and raw JSON in field hearing locations. All fixed.

**Review Cycle 4**: Rated 7/10, "would share with caveats" as a proof of concept. Remaining gaps identified:
- No speaker diarization (all speech rendered as continuous text)
- Whisper base.en produces adequate but not excellent accuracy
- Proper noun errors, especially for less common names

**Final improvements after Cycle 4**: Added RSS feed, fixed remaining location display whitespace, applied clean_title filter to committee pages.

The 7/10 rating reflects that this is a genuine proof of concept with real utility, but achieving 8+/10 would require speaker diarization (a significant engineering challenge requiring additional ML models) or a larger Whisper model (trading processing time for accuracy).

---

## Technical Decisions and Tradeoffs

**Whisper base.en vs. larger models**: I used the base.en model (74M parameters) for transcription. Larger models (small, medium, large) would improve accuracy significantly, especially for proper nouns, but would increase processing time from ~10 minutes per hour of audio to potentially hours per hearing. For a demonstration project, base.en provides the best time-to-quality tradeoff.

**Static site vs. dynamic application**: I chose a static site generator (Jinja2 → HTML) deployed on GitHub Pages rather than a server-side application. This eliminates hosting costs, scales infinitely for reads, requires no server maintenance, and is appropriate for content that updates at most a few times per week.

**Extractive vs. abstractive summarization**: Rather than using an LLM for abstractive summarization (which could introduce hallucinations), I implemented extractive summarization that selects the most substantive actual passages from the hearing. This ensures the "Key Excerpts" section contains only words actually spoken.

**No speaker diarization**: Speaker identification would significantly improve transcript utility but requires either a separate ML model (like pyannote) or a multimodal approach. Given the complexity and the project scope, I prioritized breadth of coverage over this feature, while clearly labeling transcripts as lacking speaker attribution.

---

## What Would Improve This Further

1. **Speaker diarization**: The single most impactful improvement. Technologies like pyannote.audio could segment audio by speaker, making transcripts dramatically more useful.

2. **Larger Whisper model**: Moving to `small.en` or `medium.en` would noticeably improve transcription accuracy, especially for proper nouns.

3. **Automated pipeline**: A cron job or GitHub Action that monitors for new hearings and automatically processes them would make this a truly self-updating resource.

4. **Name correction dictionary**: A curated dictionary of congressional member names and common hearing terminology could post-process transcripts to fix systematic Whisper errors.

5. **House hearing coverage**: Reliable House hearing video access (potentially through direct relationships with committee offices rather than YouTube) would double the coverage.

---

## Project Statistics

| Metric | Value |
|--------|-------|
| Hearings transcribed | 13 |
| Committees covered | 8 |
| Total audio processed | ~36 hours |
| Total words transcribed | ~294,000 |
| Total transcript segments | ~25,900 |
| Python source modules | 7 |
| HTML templates | 5 |
| Git commits | 14 |
| Chambers covered | House and Senate |

---

## Conclusion

This project demonstrates that AI can meaningfully close the transparency gap in congressional hearing access. A fully automated pipeline—from hearing discovery through audio extraction, transcription, summarization, e-book generation, and web publication—can produce usable transcripts within hours of a hearing taking place, compared to the year or more required for official transcripts.

The system works end-to-end today, and all 13 hearing transcripts are publicly accessible. The primary limitations (no speaker identification, occasional name errors) are clearly labeled and represent known engineering challenges rather than fundamental barriers. With continued development—particularly speaker diarization and automated scheduling—this could become a daily-use resource for congressional staff, journalists, researchers, and the public.
