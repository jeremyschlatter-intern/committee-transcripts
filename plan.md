# Committee Proceeding Transcripts - Implementation Plan

## Problem
Congressional committee hearing transcripts take a year+ to become available from Congress, or you have to pay a private service. We'll build a system that creates immediate transcripts and makes them freely available.

## Architecture

### Data Sources
1. **House committees**: YouTube embeds (extract via yt-dlp) - Congress.gov API for discovery
2. **Senate committees**: Akamai HLS streams via ISVP URLs - senatecommitteehearings.com CSV for discovery
3. **House floor**: Azure Front Door streams with WebVTT captions + Live Proxy API
4. **Congress.gov API**: Metadata, witness lists, committee info, related bills

### Core Pipeline
1. **Discovery**: Poll Congress.gov API + scrape committee pages for new hearings
2. **Audio Extraction**: yt-dlp for YouTube sources, ffmpeg for HLS streams
3. **Transcription**: OpenAI Whisper (local, free) for speech-to-text
4. **Speaker Diarization**: Consider pyannote.audio or simple heuristic approach
5. **Summarization**: Use Claude API or local model to generate summaries
6. **Publishing**: Static site (Hugo or custom) deployed to GitHub Pages or similar

### Static Website
- Browse by committee, date, chamber
- Full transcript view with search
- AI-generated summary for each hearing
- Download as EPUB
- Link to original video source
- Link to Unified Hearing & Markup Data when available

### Tech Stack
- **Python** for the pipeline (transcription, data processing)
- **Whisper** (openai-whisper) for transcription
- **yt-dlp** for video/audio download
- **ffmpeg** for audio processing
- **ebooklib** for EPUB generation
- **Static site generator** (likely custom with Jinja2, or 11ty/Hugo)
- **GitHub Pages** for hosting (free, static)

## Implementation Phases

### Phase 1: Core Infrastructure
- Set up project structure
- Build Congress.gov API client
- Build hearing discovery module
- Audio extraction pipeline (yt-dlp + ffmpeg)

### Phase 2: Transcription
- Whisper integration for audio-to-text
- Transcript formatting and cleanup
- Basic speaker identification

### Phase 3: Website
- Static site generator
- Hearing index pages (by committee, date, chamber)
- Individual transcript pages
- Search functionality
- Mobile-responsive design

### Phase 4: Summaries & EPUB
- AI-generated summaries
- EPUB export per hearing
- Batch processing for recent hearings

### Phase 5: Polish & Deploy
- Process a set of real recent hearings
- Deploy to GitHub Pages
- Cross-reference with Unified Hearing data
- Performance and UX polish

## Key Decisions
- Use Whisper locally (free, no API costs, good quality)
- Start with recent hearings to demonstrate value
- Focus on House committee hearings first (YouTube = easiest audio source)
- Static site for simplicity and free hosting
