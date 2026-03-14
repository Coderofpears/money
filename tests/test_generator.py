from pathlib import Path
from yt_shorts_generator import (
    CONTENT_TYPE_GUIDES,
    GeneratedPlan,
    get_source_material,
    normalize_content_type,
    parse_json_response,
    synthesize_voiceover_to_file,
    ensure_assets_structure,
    fetch_reddit_post,
)


def test_normalize_content_type_aliases():
    assert normalize_content_type("hypotheticalscenerios") == "hypothetical"
    assert normalize_content_type("funny-reddit") == "funny_reddit"
    assert normalize_content_type("roblox-rant") == "roblox_rant"


def test_get_source_material_roblox_rant():
    source = get_source_material("roblox_rant", "Obbies are all cash grabs")
    assert "Rant focus" in source.body


def test_get_source_material_reddit_fallback(monkeypatch):
    def _fail(*args, **kwargs):
        raise RuntimeError("network blocked")

    monkeypatch.setattr("yt_shorts_generator.fetch_reddit_post", _fail)
    source = get_source_material("reddit_story", "topic")
    assert source.title.startswith("Fallback")
    assert source.subreddit == "fallback"


def test_generated_plan_model_fields():
    plan = GeneratedPlan(
        title="t",
        hook="h",
        script="s",
        cta="c",
    )
    assert isinstance(plan.hashtags, list)
    assert set(CONTENT_TYPE_GUIDES.keys()) >= {"roblox_rant", "reddit_story", "hypothetical", "funny_reddit"}


def test_parse_json_response_with_markdown_wrapper():
    payload = parse_json_response("```json\n{\"a\": 1}\n```")
    assert payload["a"] == 1


def test_synthesize_voiceover_fails_gracefully(monkeypatch, tmp_path):
    class FailingTTS:
        def __init__(self, *args, **kwargs):
            pass
        def save(self, *_args, **_kwargs):
            raise RuntimeError("tts down")

    monkeypatch.setattr("yt_shorts_generator.gTTS", FailingTTS)
    out = tmp_path / "audio.mp3"
    ok = synthesize_voiceover_to_file("hello", str(out))
    assert ok is False


def test_render_video_uses_silent_fallback_when_tts_fails(monkeypatch, tmp_path):
    import yt_shorts_generator as mod

    class DummyClip:
        def __init__(self):
            self.duration = 12
        def set_duration(self, *_args, **_kwargs):
            return self
        def set_audio(self, _audio):
            return self
        def write_videofile(self, path, **_kwargs):
            Path(path).write_bytes(b"video")
        def close(self):
            pass

    class DummyText:
        def set_position(self, *_args, **_kwargs):
            return self
        def set_duration(self, *_args, **_kwargs):
            return self
        def set_start(self, *_args, **_kwargs):
            return self

    monkeypatch.setattr(mod, "synthesize_voiceover_to_file", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(mod, "make_silent_audio", lambda *_args, **_kwargs: DummyClip())
    monkeypatch.setattr(mod, "ColorClip", lambda *_args, **_kwargs: DummyClip())
    monkeypatch.setattr(mod, "TextClip", lambda *_args, **_kwargs: DummyText())
    monkeypatch.setattr(mod, "CompositeVideoClip", lambda *_args, **_kwargs: DummyClip())

    plan = mod.GeneratedPlan(title="t", hook="h", script="s", cta="c")
    out = tmp_path / "out.mp4"
    mod.render_video(plan, str(out))

    assert out.exists()


def test_ensure_assets_structure_creates_expected_folders(tmp_path):
    dirs = ensure_assets_structure(tmp_path / "assets")
    for key in ("root", "backgrounds", "music", "outputs", "plans", "analysis"):
        assert dirs[key].exists()


def test_fetch_reddit_post_supports_top_week(monkeypatch):
    class DummyResp:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Test title",
                                "selftext": "Body",
                                "permalink": "/r/test/comments/abc/test/",
                            }
                        }
                    ]
                }
            }

    captured = {}

    def _fake_get(url, headers=None, params=None, timeout=0):
        captured["url"] = url
        captured["params"] = params
        return DummyResp()

    monkeypatch.setattr("yt_shorts_generator.requests.get", _fake_get)
    source = fetch_reddit_post("AskReddit", sort="top_week")

    assert source.title == "Test title"
    assert captured["url"].endswith("/top.json")
    assert captured["params"]["t"] == "week"
