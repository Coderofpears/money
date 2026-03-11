from yt_shorts_generator import (
    CONTENT_TYPE_GUIDES,
    GeneratedPlan,
    get_source_material,
    normalize_content_type,
    parse_json_response,
    synthesize_voiceover_to_file,
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
