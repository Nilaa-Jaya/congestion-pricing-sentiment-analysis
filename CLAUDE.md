# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube comment scraper for research on "NYC congestion pricing". Fetches videos via YouTube Data API v3, collects all top-level comments with pagination, and exports to timestamped CSV files with rich video metadata.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Create `.env` file with `YOUTUBE_API_KEY=your_key_here`
3. Get API key from: https://console.cloud.google.com/apis/credentials

## Usage

**Basic scraping:**
```bash
python youtube.py                           # Default: 10 videos, "NYC congestion pricing"
python youtube.py -n 50                     # Scrape 50 videos
python youtube.py -q "your query" -n 20     # Custom query and count
python youtube.py -o custom.csv             # Custom output file
```

**Analysis:**
```bash
python youtube.py -a data/youtube_comments_20250930_1445.csv
```

**In Python:**
```python
from youtube import load_comments

df = load_comments()                        # Auto-loads latest CSV from data/
df = load_comments('path/to/file.csv')      # Load specific file
```

## Architecture

**Single-file architecture** (`youtube.py`) with functional pipeline:

1. **Search phase:** `search_videos()` → `get_video_details()`
   - Searches by query, returns video IDs ranked by YouTube's relevance
   - Enriches with statistics (views, likes, duration, description)
   - Duration converted from ISO 8601 to seconds via `parse_duration()`

2. **Collection phase:** `get_video_comments()` per video
   - Fetches all top-level comments with pagination (100/request)
   - Handles disabled comments gracefully
   - Does NOT fetch replies (would require separate API calls)

3. **Export phase:** `scrape_comments()` orchestrates everything
   - Merges video metadata with each comment
   - Saves to `data/youtube_comments_YYYYMMDD_HHMM.csv`
   - Creates `data/` directory automatically

4. **Analysis utilities:**
   - `load_comments()`: Loads CSV with proper type conversions (datetimes, integers)
   - `--analyze` flag: Shows quick stats (comment count, top authors, most liked)

## CSV Schema

**Video metadata (repeated per comment):**
- `video_id`, `relevance_rank`, `video_title`, `video_channel`
- `video_published_at`, `video_view_count`, `video_like_count`, `video_comment_count`
- `video_duration` (seconds), `video_description`

**Comment data:**
- `author`, `comment_text`, `comment_like_count`, `comment_published_at`

Note: Two separate date columns distinguish when video was uploaded vs when comment was posted.

## API Quota Management

- Free tier: 10,000 units/day
- Search: 100 units per query
- Comments: 1 unit per page (100 comments)
- Video details: 1 unit per batch (up to 50 IDs)
- Roughly ~100 videos + comments/day within quota

## Code Conventions

- Use tabs, not spaces
- No emojis
- Straight quotes only (never curly)
- Keep descriptions concise
- Never commit `.env` or CSV files (gitignored)
