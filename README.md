# AI YouTube Shorts Generator (Groq Powered)

This project generates YouTube-Short-style videos using AI with Groq, and supports **multiple video formats** (story, listicle, tutorial, opinion/hot-take, motivational).

It can also **analyze a reference YouTube video** (like your provided URL) by pulling metadata/transcript and extracting style hints used to steer generation.

## Features

- Groq-powered generation of:
  - hook
  - scene-by-scene script
  - captions
  - CTA
  - title + hashtags
- Reference video analysis from URL:
  - transcript summary
  - speaking speed estimate
  - recurring patterns/hook style
- Multiple short-video types:
  - `story`
  - `listicle`
  - `tutorial`
  - `hot_take`
  - `motivation`
- Multiple content-source types:
  - `general` (normal topic)
  - `roblox_rant`
  - `reddit_story` (from subreddit posts)
  - `hypothetical` (from hypothetical scenario subreddits; aliases like `hypotheticalscenerios` are accepted)
  - `funny_reddit` (from funny subreddit posts)
- Auto video rendering pipeline:
  - voiceover via TTS (`gTTS`)
  - stock-style background (solid/gradient)
  - dynamic text overlays
  - subtitle-like captions
  - exported MP4 ready for Shorts/Reels/TikTok

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set Groq API key:

```bash
export GROQ_API_KEY="your_key_here"
```

Install ffmpeg (required by moviepy).

## Usage

### 1) Analyze an existing short

```bash
python yt_shorts_generator.py analyze \
  --url "https://www.youtube.com/shorts/jyX8fMA5gF8" \
  --out analysis.json
```

### 2) Generate a new short script (AI)

```bash
python yt_shorts_generator.py generate \
  --topic "How to build discipline in 7 days" \
  --video-type motivation \
  --content-type general \
  --duration 30 \
  --analysis-file analysis.json \
  --out generated_plan.json
```

### Reddit story example

```bash
python yt_shorts_generator.py generate \
  --topic "crazy relationship drama" \
  --video-type story \
  --content-type reddit_story \
  --subreddit AmItheAsshole \
  --duration 35 \
  --out reddit_story_plan.json
```

### Roblox rant example

```bash
python yt_shorts_generator.py generate \
  --topic "Roblox games are too pay-to-win now" \
  --video-type hot_take \
  --content-type roblox_rant \
  --duration 30 \
  --out roblox_rant_plan.json
```

### 3) Render the final video

```bash
python yt_shorts_generator.py render \
  --plan generated_plan.json \
  --out output_short.mp4
```

## End-to-end

```bash
python yt_shorts_generator.py full \
  --topic "funniest awkward social moment" \
  --video-type story \
  --content-type funny_reddit \
  --subreddit AskReddit \
  --duration 30 \
  --reference-url "https://www.youtube.com/shorts/jyX8fMA5gF8" \
  --out output_short.mp4
```

## Notes

- If transcript extraction fails for a video, generation still works without analysis data.
- If `gTTS` fails (network/rate limits), renderer falls back to silent audio so MP4 export still succeeds.
- You can customize prompts in `yt_shorts_generator.py` for your niche and language.
- For better visuals, replace the basic background generator with b-roll APIs or local clips.
