"""Tests for the optional spoken status. Nothing here talks to ElevenLabs:
a stand-in makes the audio, and a stand-in plays it.

Run either way:
    python tests/test_voice.py
    python -m pytest tests -q
"""

import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitcheck import voice as voice_module  # noqa: E402
from kitcheck.voice import (  # noqa: E402
    PHRASES,
    Settings,
    Voice,
    VoiceError,
    build,
    key_for_verdict,
    lines,
    read_index,
    render,
    synthesize,
)


class Calls:
    """Stand-in for the ElevenLabs call: remembers what it was asked to say."""

    def __init__(self):
        self.texts = []

    def __call__(self, text, settings, api_key):
        self.texts.append(text)
        return b"AUDIO:" + text.encode()


class Player:
    """Stand-in for the audio player: remembers what it was asked to play."""

    def __init__(self, fail=False):
        self.commands = []
        self.fail = fail
        self.stopped = 0

    def __call__(self, command, **_):
        if self.fail:
            raise OSError("no sound device")
        self.commands.append(command)
        return self

    def poll(self):
        return None  # still playing

    def terminate(self):
        self.stopped += 1

    def wait(self, timeout=None):
        return 0


def settings_in(folder, **changes):
    values = {"enabled": True, "voice_id": "voice-1", "clips": str(Path(folder) / "voice")}
    values.update(changes)
    return Settings(**values)


def test_sentences_fill_in_the_item():
    assert render("kit_ready") == "Kit ready."
    assert render("picking", "sensor") == "Picking the sensor."
    assert render("verified", "motor") == "Motor placed."
    assert render("restock", "sensor") == "Please put a sensor on its square."
    assert render("restock", "encoder") == "Please put an encoder on its square."
    assert render("incomplete", "encoder") == "The kit is incomplete. An encoder is missing."
    try:
        render("picking")
    except KeyError:
        pass
    else:
        raise AssertionError("a phrase about an item needs the item")


def test_every_phrase_is_listed_once_per_item():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        names = [name for name, _, _ in lines(settings)]
        assert len(names) == len(set(names))
        assert "kit_ready" in names and "picking:sensor" in names and "picking:motor" in names
        files = [file_name for _, _, file_name in lines(settings)]
        assert len(files) == len(set(files))
        per_item = sum("{" in template for template in PHRASES.values())
        assert len(names) == (len(PHRASES) - per_item) + 2 * per_item


def test_build_makes_each_clip_once_and_keeps_them():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        calls = Calls()
        made, kept, characters = build(settings, api_key="k", make=calls, report=lambda _: None)
        total = len(lines(settings))
        assert (made, kept) == (total, 0)
        assert characters == sum(len(text) for _, text, _ in lines(settings))
        assert (Path(settings.clips) / "kit_ready.mp3").read_bytes() == b"AUDIO:Kit ready."
        index = read_index(settings)
        assert index["voice_id"] == "voice-1" and len(index["clips"]) == total

        again = Calls()
        assert build(settings, api_key="k", make=again, report=lambda _: None)[:2] == (0, total)
        assert again.texts == []


def test_build_needs_no_key_when_nothing_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        build(settings, api_key="k", make=Calls(), report=lambda _: None)
        saved = voice_module.os.environ.pop(voice_module.KEY_VARIABLE, None)
        try:
            assert build(settings, make=Calls(), report=lambda _: None)[0] == 0
        finally:
            if saved is not None:
                voice_module.os.environ[voice_module.KEY_VARIABLE] = saved


def test_build_without_a_key_explains_what_to_do():
    with tempfile.TemporaryDirectory() as tmp:
        saved = voice_module.os.environ.pop(voice_module.KEY_VARIABLE, None)
        try:
            build(settings_in(tmp), make=Calls(), report=lambda _: None)
        except VoiceError as error:
            assert voice_module.KEY_VARIABLE in str(error)
        else:
            raise AssertionError("expected a VoiceError")
        finally:
            if saved is not None:
                voice_module.os.environ[voice_module.KEY_VARIABLE] = saved


def test_changing_the_voice_or_items_rebuilds_only_what_changed():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        build(settings, api_key="k", make=Calls(), report=lambda _: None)
        total = len(lines(settings))

        # A new item: only its lines are made, the rest are kept.
        settings.items = {"sensor": "sensor", "motor": "motor", "encoder": "encoder"}
        calls = Calls()
        made, kept, _ = build(settings, api_key="k", make=calls, report=lambda _: None)
        assert kept == total and made == len(lines(settings)) - total
        assert all("encoder" in text.lower() for text in calls.texts)

        # Dropping an item removes its lines from the index.
        settings.items = {"sensor": "sensor"}
        build(settings, api_key="k", make=Calls(), report=lambda _: None)
        assert not any(name.endswith(":motor") for name in read_index(settings)["clips"])

        # A different voice: everything is made again.
        settings.voice_id = "voice-2"
        made, kept, _ = build(settings, api_key="k", make=Calls(), report=lambda _: None)
        assert kept == 0 and made == len(lines(settings))


def test_an_interrupted_build_keeps_what_it_made():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)

        def fails_on_third(text, _settings, _key, count=[0]):
            count[0] += 1
            if count[0] == 3:
                raise VoiceError("ElevenLabs refused the request: quota exceeded")
            return b"AUDIO"

        try:
            build(settings, api_key="k", make=fails_on_third, report=lambda _: None)
        except VoiceError:
            pass
        assert len(read_index(settings)["clips"]) == 2
        made, kept, _ = build(settings, api_key="k", make=Calls(), report=lambda _: None)
        assert kept == 2 and made == len(lines(settings)) - 2


def test_voice_plays_a_saved_clip():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        build(settings, api_key="k", make=Calls(), report=lambda _: None)
        player = Player()
        voice = Voice(settings, player=["play"], start=player)
        assert voice.say("picking", "sensor") is True
        assert player.commands[-1] == ["play", str(Path(settings.clips) / "picking-sensor.mp3")]
        assert voice.say("kit_ready") is True
        assert player.stopped == 1  # the first clip was cut off, not talked over
        assert voice.clip_for("kit_ready").name == "kit_ready.mp3"


def test_voice_stays_quiet_and_never_raises():
    with tempfile.TemporaryDirectory() as tmp:
        settings = settings_in(tmp)
        build(settings, api_key="k", make=Calls(), report=lambda _: None)

        off = Voice(settings_in(tmp, enabled=False), player=["play"], start=Player())
        assert off.say("kit_ready") is False

        voice = Voice(settings, player=["play"], start=Player(fail=True))
        assert voice.say("kit_ready") is False            # the player failed
        assert voice.say("no_such_phrase") is False       # unknown phrase
        assert voice.say("picking") is False              # item missing
        assert voice.say("picking", "widget") is False    # no clip for that item

        empty = Voice(settings_in(Path(tmp) / "elsewhere"), player=["play"], start=Player())
        assert empty.say("kit_ready") is False            # clips never built
        assert empty.clip_for("kit_ready") is None


def test_settings_come_from_config_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(
            json.dumps(
                {
                    "items": {"sensor": {"label": "Sensor"}, "encoder": {"label": "Rotary Encoder"}},
                    "voice": {"enabled": True, "voice_id": "abc", "clips": "somewhere"},
                }
            )
        )
        settings = Settings.from_config(path)
        assert settings.enabled and settings.voice_id == "abc" and settings.clips == "somewhere"
        assert settings.items == {"sensor": "sensor", "encoder": "rotary encoder"}
        assert settings.model_id == "eleven_multilingual_v2"

        missing = Settings.from_config(Path(tmp) / "nothing.json")
        assert missing.enabled is False and "sensor" in missing.items


def test_grasp_verdicts_map_to_phrases():
    assert key_for_verdict("placed") == "verified"
    assert key_for_verdict("held") == "verified"
    assert key_for_verdict("missed") == "missed"
    assert key_for_verdict("missed", attempt=1) == "missed_retry"
    assert key_for_verdict("missed", attempt=2) == "missed_twice"
    assert key_for_verdict("dropped", "the object slipped out of the gripper") == "dropped_slipped"
    assert key_for_verdict("dropped", "was still holding the object when the run ended") == "dropped_timeout"
    assert key_for_verdict("dropped", "let go 25 units away from its bin") == "dropped_wrong_place"
    assert key_for_verdict("error") == "error"
    assert all(key_for_verdict(o, r) in PHRASES for o in ("placed", "missed", "dropped", "error") for r in ("", "slipped"))


def test_a_refused_request_reports_the_reason():
    # ElevenLabs answers a bad key with HTTP 401 and a JSON body like this.
    body = json.dumps({"detail": {"type": "authentication_error", "message": "Invalid API key"}}).encode()

    def refuse(request, timeout=None):
        assert request.get_header("Xi-api-key") == "bad"
        assert "/v1/text-to-speech/voice-1" in request.full_url and "output_format=mp3_44100_128" in request.full_url
        assert json.loads(request.data) == {"text": "Kit ready.", "model_id": "eleven_multilingual_v2"}
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(body))

    original = voice_module.urllib.request.urlopen
    voice_module.urllib.request.urlopen = refuse
    try:
        synthesize("Kit ready.", Settings(voice_id="voice-1"), "bad")
    except VoiceError as error:
        assert "Invalid API key" in str(error) and "bad" not in str(error)
    else:
        raise AssertionError("expected a VoiceError")
    finally:
        voice_module.urllib.request.urlopen = original

    try:
        synthesize("Kit ready.", Settings(), "key")
    except VoiceError as error:
        assert "no voice chosen" in str(error)
    else:
        raise AssertionError("expected a VoiceError")


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"ok    {name}")
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {name}: {error!r}")
    sys.exit(1 if failures else 0)
