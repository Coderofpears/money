#!/usr/bin/env python3
import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from gtts import gTTS
from groq import Groq
from moviepy import AudioClip, AudioFileClip, ColorClip, CompositeVideoClip, TextClip
from pydantic import BaseModel, Field
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp


VIDEO_TYPE_GUIDES = {
    "story": "Narrative arc: hook -> conflict -> twist -> payoff -> CTA.",
    "listicle": "Fast top-N format with numbered beats and punchy transitions.",
    "tutorial": "Problem -> 3 to 5 actionable steps -> rapid recap -> CTA.",
    "hot_take": "Contrarian opinion with bold hook, evidence, and challenge CTA.",
    "motivation": "Emotion-driven hook, identity shift framing, and direct challenge CTA.",
}


CONTENT_TYPE_GUIDES = {
    "general": "Use the provided topic as-is.",
    "roblox_rant": "Write like a bold, energetic Roblox rant with gamer slang and strong opinions.",
    "reddit_story": "Turn a Reddit post into a story arc with setup, conflict, and payoff.",
    "hypothetical": "Use a mind-bending what-if scenario and explore likely outcomes quickly.",
    "funny_reddit": "Use comedic Reddit content with punchlines and relatable social awkwardness.",
}

CONTENT_TYPE_ALIASES = {
    "roblox-rant": "roblox_rant",
    "reddit-stories": "reddit_story",
    "reddit_story": "reddit_story",
    "hypotheticalscenerios": "hypothetical",
    "hypotheticalscenarios": "hypothetical",
    "hypothetical-scenarios": "hypothetical",
    "funny_reddit_posts": "funny_reddit",
    "funny-reddit": "funny_reddit",
}

DEFAULT_SUBREDDITS = {
    "reddit_story": ["AmItheAsshole", "tifu", "offmychest", "TrueOffMyChest"],
    "hypothetical": ["hypotheticalsituation", "hypothetical", "whatif"],
    "funny_reddit": ["funny", "AskReddit", "therewasanattempt", "memes"],
}

FALLBACK_REDDIT_SEEDS = {
    "reddit_story": "A friend borrowed money, ghosted for months, then asked for more.",
    "hypothetical": "What if every person could read minds for just 10 seconds per day?",
    "funny_reddit": "Someone confidently waved back at a stranger for 2 minutes, then realized it was not for them.",
}




def normalize_content_type(content_type: str) -> str:
    key = (content_type or "general").strip().lower()
    return CONTENT_TYPE_ALIASES.get(key, key)


def parse_json_response(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class GeneratedPlan(BaseModel):
    title: str
    hook: str
    script: str
    cta: str
    hashtags: List[str] = Field(default_factory=list)
    scenes: List[str] = Field(default_factory=list)
    captions: List[str] = Field(default_factory=list)
    visual_style_notes: str = ""
    voice_style_notes: str = ""


@dataclass
class VideoAnalysis:
    url: str
    title: str
    description: str
    duration_sec: Optional[int]
    transcript_excerpt: str
    transcript_word_count: int
    style_summary: str


@dataclass
class SourceMaterial:
    title: str
    body: str
    subreddit: Optional[str] = None
    url: Optional[str] = None


def extract_video_id(url: str) -> str:
    patterns = [
        r"youtube\.com/shorts/([a-zA-Z0-9_-]+)",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not parse YouTube video ID from URL")


def fetch_video_metadata(url: str) -> Dict[str, Any]:
    options = {"quiet": True, "skip_download": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "duration": info.get("duration"),
    }


def fetch_transcript(video_id: str) -> str:
    transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
    return " ".join(chunk.get("text", "") for chunk in transcript_data)


def call_groq_json(system_prompt: str, user_prompt: str, model: str = "llama-3.1-70b-versatile") -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set")

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    text = completion.choices[0].message.content
    return parse_json_response(text)


def fetch_reddit_post(subreddit: str, sort: str = "hot") -> SourceMaterial:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit=15"
    headers = {"User-Agent": "yt-shorts-generator/1.0"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    payload = response.json()

    posts = payload.get("data", {}).get("children", [])
    for post in posts:
        data = post.get("data", {})
        title = (data.get("title") or "").strip()
        self_text = (data.get("selftext") or "").strip()
        if not title:
            continue
        body = self_text if self_text else "No body text provided. Use title-driven storytelling."
        permalink = data.get("permalink")
        full_url = f"https://reddit.com{permalink}" if permalink else None
        return SourceMaterial(title=title, body=body[:3000], subreddit=subreddit, url=full_url)

    raise ValueError(f"No suitable posts found in r/{subreddit}")


def get_source_material(content_type: str, topic: str, subreddit: Optional[str] = None) -> SourceMaterial:
    content_type = normalize_content_type(content_type)

    if content_type == "general":
        return SourceMaterial(title=topic, body=topic)

    if content_type == "roblox_rant":
        rant_seed = topic if topic else "Roblox is getting less fun because every game feels pay-to-win"
        return SourceMaterial(
            title="Roblox rant seed",
            body=f"Rant focus: {rant_seed}. Include specific examples, frustrations, and gamer-style reactions.",
        )

    if content_type in {"reddit_story", "hypothetical", "funny_reddit"}:
        picks = [subreddit] if subreddit else DEFAULT_SUBREDDITS[content_type]
        last_error = None
        for sub in picks:
            try:
                return fetch_reddit_post(sub)
            except Exception as exc:
                last_error = exc
                continue
        fallback = FALLBACK_REDDIT_SEEDS[content_type]
        return SourceMaterial(
            title=f"Fallback {content_type} seed",
            body=f"Live Reddit fetch unavailable. Use this seed instead: {fallback}",
            subreddit=subreddit or "fallback",
            url=None,
        )

    raise ValueError(f"Unsupported content type: {content_type}")


def analyze_reference_video(url: str) -> VideoAnalysis:
    metadata = fetch_video_metadata(url)
    video_id = extract_video_id(url)

    transcript = ""
    try:
        transcript = fetch_transcript(video_id)
    except Exception:
        transcript = ""

    excerpt = transcript[:2000]

    system_prompt = (
        "You are an expert short-form video analyst. "
        "Return valid JSON with key 'style_summary'."
    )
    user_prompt = (
        f"Analyze this short video metadata/transcript and infer style patterns.\n"
        f"Title: {metadata['title']}\n"
        f"Description: {metadata['description'][:1000]}\n"
        f"Duration: {metadata['duration']}\n"
        f"Transcript excerpt: {excerpt}\n"
        "Describe hook style, pacing, sentence length, emotional tone, and CTA patterns."
    )

    try:
        analysis_json = call_groq_json(system_prompt, user_prompt)
        style_summary = analysis_json.get("style_summary", "")
    except Exception:
        style_summary = "Could not generate AI style summary; fallback to metadata-only analysis."

    return VideoAnalysis(
        url=url,
        title=metadata["title"],
        description=metadata["description"],
        duration_sec=metadata["duration"],
        transcript_excerpt=excerpt,
        transcript_word_count=len(transcript.split()),
        style_summary=style_summary,
    )


def generate_plan(
    topic: str,
    video_type: str,
    duration_sec: int,
    analysis: Optional[VideoAnalysis] = None,
    content_type: str = "general",
    subreddit: Optional[str] = None,
) -> GeneratedPlan:
    if video_type not in VIDEO_TYPE_GUIDES:
        raise ValueError(f"Unsupported video type: {video_type}. Use one of: {', '.join(VIDEO_TYPE_GUIDES.keys())}")

    content_type = normalize_content_type(content_type)
    if content_type not in CONTENT_TYPE_GUIDES:
        raise ValueError(f"Unsupported content type: {content_type}. Use one of: {', '.join(CONTENT_TYPE_GUIDES.keys())}")

    source = get_source_material(content_type, topic, subreddit)

    analysis_block = "No reference analysis provided."
    if analysis:
        analysis_block = (
            f"Reference title: {analysis.title}\n"
            f"Reference duration: {analysis.duration_sec}\n"
            f"Reference style summary: {analysis.style_summary}\n"
            f"Reference transcript words: {analysis.transcript_word_count}\n"
        )

    system_prompt = (
        "You generate high-retention YouTube Shorts plans. "
        "Always return JSON with keys: title, hook, script, cta, hashtags, scenes, captions, visual_style_notes, voice_style_notes."
    )

    user_prompt = (
        f"Create a {duration_sec}-second short about: {topic}.\n"
        f"Video type: {video_type}.\n"
        f"Content type: {content_type}.\n"
        f"Style guide: {VIDEO_TYPE_GUIDES[video_type]}\n"
        f"Content guide: {CONTENT_TYPE_GUIDES[content_type]}\n"
        f"Source title: {source.title}\n"
        f"Source body: {source.body}\n"
        f"Source subreddit: {source.subreddit}\n"
        f"Source URL: {source.url}\n"
        f"Reference analysis: {analysis_block}\n"
        "Constraints:\n"
        "- Hook in first 2 seconds\n"
        "- Keep language simple and punchy\n"
        "- 5 to 8 short scenes\n"
        "- Captions per scene\n"
        "- Add 6 to 12 relevant hashtags"
    )

    response = call_groq_json(system_prompt, user_prompt)
    return GeneratedPlan.model_validate(response)



def synthesize_voiceover_to_file(text: str, audio_path: str) -> bool:
    try:
        gTTS(text=text, lang="en").save(audio_path)
        return True
    except Exception:
        return False


def make_silent_audio(duration: float) -> AudioClip:
    return AudioClip(lambda t: np.zeros_like(t, dtype=float), duration=duration, fps=44100)

def render_video(plan: GeneratedPlan, output_path: str) -> None:
    width, height = 1080, 1920

    narration_text = " ".join([plan.hook, plan.script, plan.cta]).strip() or "Generated short video"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_tmp:
        audio_path = audio_tmp.name

    has_tts_audio = synthesize_voiceover_to_file(narration_text, audio_path)
    if has_tts_audio:
        audio_clip = AudioFileClip(audio_path)
        duration = min(max(audio_clip.duration, 8), 60)
    else:
        duration = 12
        audio_clip = make_silent_audio(duration)

    bg = ColorClip(size=(width, height), color=(20, 20, 20)).set_duration(duration)

    hook_clip = (
        TextClip(
            txt=plan.hook,
            fontsize=72,
            color="white",
            size=(width - 140, None),
            method="caption",
            align="center",
        )
        .set_position(("center", 260))
        .set_duration(min(3, duration))
    )

    body_text = "\n\n".join(plan.scenes[:8] if plan.scenes else [plan.script])
    body_clip = (
        TextClip(
            txt=body_text,
            fontsize=52,
            color="white",
            size=(width - 180, None),
            method="caption",
            align="center",
        )
        .set_position(("center", "center"))
        .set_start(2)
        .set_duration(max(duration - 5, 3))
    )

    cta_clip = (
        TextClip(
            txt=plan.cta,
            fontsize=62,
            color="yellow",
            size=(width - 200, None),
            method="caption",
            align="center",
        )
        .set_position(("center", height - 360))
        .set_start(max(duration - 3, 0))
        .set_duration(3)
    )

    final = CompositeVideoClip([bg, hook_clip, body_clip, cta_clip]).set_audio(audio_clip)
    final.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac")

    final.close()
    audio_clip.close()

    try:
        os.remove(audio_path)
    except OSError:
        pass


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_analysis(path: str) -> VideoAnalysis:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return VideoAnalysis(**payload)


def load_plan(path: str) -> GeneratedPlan:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return GeneratedPlan.model_validate(payload)


def cmd_analyze(args: argparse.Namespace) -> None:
    analysis = analyze_reference_video(args.url)
    save_json(args.out, analysis.__dict__)
    print(f"Saved analysis to {args.out}")


def cmd_generate(args: argparse.Namespace) -> None:
    analysis = load_analysis(args.analysis_file) if args.analysis_file else None
    plan = generate_plan(
        args.topic,
        args.video_type,
        args.duration,
        analysis,
        content_type=args.content_type,
        subreddit=args.subreddit,
    )
    save_json(args.out, plan.model_dump())
    print(f"Saved plan to {args.out}")


def cmd_render(args: argparse.Namespace) -> None:
    plan = load_plan(args.plan)
    render_video(plan, args.out)
    print(f"Rendered video to {args.out}")


def cmd_full(args: argparse.Namespace) -> None:
    analysis = None
    if args.reference_url:
        analysis = analyze_reference_video(args.reference_url)

    plan = generate_plan(
        args.topic,
        args.video_type,
        args.duration,
        analysis,
        content_type=args.content_type,
        subreddit=args.subreddit,
    )
    render_video(plan, args.out)

    base = Path(args.out).with_suffix("")
    save_json(f"{base}_plan.json", plan.model_dump())
    if analysis:
        save_json(f"{base}_analysis.json", analysis.__dict__)

    print(f"Rendered video to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-powered YouTube Shorts generator using Groq")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Analyze a reference YouTube video")
    p_analyze.add_argument("--url", required=True, help="YouTube video/short URL")
    p_analyze.add_argument("--out", required=True, help="Output JSON path")
    p_analyze.set_defaults(func=cmd_analyze)

    p_generate = sub.add_parser("generate", help="Generate a shorts plan")
    p_generate.add_argument("--topic", required=True)
    p_generate.add_argument("--video-type", required=True, choices=list(VIDEO_TYPE_GUIDES.keys()))
    p_generate.add_argument("--content-type", default="general", help="Content source type (e.g. general, roblox_rant, reddit_story, hypothetical, funny_reddit)")
    p_generate.add_argument("--subreddit", help="Optional subreddit override for reddit-based content types")
    p_generate.add_argument("--duration", type=int, default=30)
    p_generate.add_argument("--analysis-file", help="Optional analysis JSON")
    p_generate.add_argument("--out", required=True)
    p_generate.set_defaults(func=cmd_generate)

    p_render = sub.add_parser("render", help="Render a shorts video from plan JSON")
    p_render.add_argument("--plan", required=True)
    p_render.add_argument("--out", required=True)
    p_render.set_defaults(func=cmd_render)

    p_full = sub.add_parser("full", help="Analyze (optional), generate, and render in one command")
    p_full.add_argument("--topic", required=True)
    p_full.add_argument("--video-type", required=True, choices=list(VIDEO_TYPE_GUIDES.keys()))
    p_full.add_argument("--content-type", default="general", help="Content source type (e.g. general, roblox_rant, reddit_story, hypothetical, funny_reddit)")
    p_full.add_argument("--subreddit", help="Optional subreddit override for reddit-based content types")
    p_full.add_argument("--duration", type=int, default=30)
    p_full.add_argument("--reference-url", help="Optional reference URL to mimic style")
    p_full.add_argument("--out", required=True)
    p_full.set_defaults(func=cmd_full)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
