"""Spoken status: the station says what it is doing, in a voice made with the ElevenLabs API.

This part is optional and off by default.

Everything the station can say is known in advance, so the clips are made once,
while online, and saved as files in assets/voice/. At run time KitCheck only
plays those files: no API key and no network are needed during a demo.

Use
---
    export ELEVENLABS_API_KEY=...            # keep the key out of any file you share
    python -m kitcheck.voice voices          # voices available to your account
    python -m kitcheck.voice build --voice <voice id>     # make every clip
    python -m kitcheck.voice list            # what it can say, and which clips exist
    python -m kitcheck.voice say kit_ready   # play one clip
    python -m kitcheck.voice say picking --item sensor

To hear it during runs, set "voice": {"enabled": true} in config.json.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://api.elevenlabs.io"
KEY_VARIABLE = "ELEVENLABS_API_KEY"
DEFAULT_MODEL = "eleven_multilingual_v2"   # the API's own default; quality matters more than speed for saved clips
DEFAULT_FORMAT = "mp3_44100_128"           # the API's default output format
DEFAULT_CLIPS = "assets/voice"
INDEX = "index.json"

# What the station can say. {item} is the item's name, {a_item} adds "a" or "an",
# {Item} starts with a capital. Lines without a placeholder are made once;
# the others are made once per item.
PHRASES = {
    "hello": "KitCheck is ready. Choose a kit.",
    "order_started": "Order received. Packing your kit.",
    "picking": "Picking the {item}.",
    "verified": "{Item} placed.",
    "missed": "I picked up nothing.",
    "missed_retry": "I picked up nothing. Trying again.",
    "missed_twice": "I picked up nothing twice. Is there {a_item} on its square?",
    "dropped_slipped": "The {item} slipped out of my gripper. I need a hand.",
    "dropped_wrong_place": "I let go of the {item} away from the tray. I need a hand.",
    "dropped_timeout": "I ran out of time while holding the {item}. I need a hand.",
    "error": "The robot run failed. Please check the screen.",
    "kit_ready": "Kit ready.",
    "restock": "Please put {a_item} on its square.",
    "unconfirmed": "I let go at the tray, but I can't see a new {item} in it.",
    "incomplete": "The kit is incomplete. {A_item} is missing.",
    "collected": "Kit collected. Thank you.",
}


class VoiceError(Exception):
    """Something the person can act on: no key, a refused request, no voice chosen."""


@dataclass
class Settings:
    enabled: bool = False
    voice_id: str = ""
    model_id: str = DEFAULT_MODEL
    output_format: str = DEFAULT_FORMAT
    clips: str = DEFAULT_CLIPS
    items: dict = field(default_factory=lambda: {"sensor": "sensor", "motor": "motor"})  # item -> spoken name

    @classmethod
    def from_config(cls, path="config.json"):
        """Read the "voice" section and the item names from config.json; defaults if there is none."""
        settings = cls()
        path = Path(path)
        if not path.is_file():
            return settings
        config = json.loads(path.read_text())
        voice = config.get("voice", {})
        settings.enabled = bool(voice.get("enabled", False))
        settings.voice_id = voice.get("voice_id", "") or ""
        settings.model_id = voice.get("model_id", DEFAULT_MODEL) or DEFAULT_MODEL
        settings.output_format = voice.get("output_format", DEFAULT_FORMAT) or DEFAULT_FORMAT
        settings.clips = voice.get("clips", DEFAULT_CLIPS) or DEFAULT_CLIPS
        items = config.get("items")
        if items:
            settings.items = {name: str(entry.get("label", name)).lower() for name, entry in items.items()}
        return settings


# ---------------------------------------------------------------------------
# The lines


def _article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def render(key, spoken_item=None):
    """The sentence for one phrase, with the item's name filled in."""
    template = PHRASES[key]
    if "{" not in template:
        return template
    if not spoken_item:
        raise KeyError(f"phrase '{key}' needs an item")
    a_item = f"{_article(spoken_item)} {spoken_item}"
    return template.format(
        item=spoken_item,
        Item=spoken_item[:1].upper() + spoken_item[1:],
        a_item=a_item,
        A_item=a_item[:1].upper() + a_item[1:],
    )


def needs_item(key):
    return "{" in PHRASES[key]


def clip_name(key, item=None):
    """Name used in the index: 'kit_ready' or 'picking:sensor'."""
    return f"{key}:{item}" if needs_item(key) else key


def lines(settings):
    """Every (name, sentence, file name) the station can say with the current items."""
    result = []
    for key in PHRASES:
        if needs_item(key):
            for item, spoken in settings.items.items():
                result.append((clip_name(key, item), render(key, spoken), f"{key}-{item}.mp3"))
        else:
            result.append((key, render(key), f"{key}.mp3"))
    return result


def key_for_verdict(outcome, reason="", attempt=None):
    """Which phrase goes with a grasp verdict (see kitcheck/grasp.py).

    attempt is the attempt number inside an order; leave it out for a single test pick.
    """
    if outcome in ("placed", "held"):
        return "verified"
    if outcome == "missed":
        if attempt is None:
            return "missed"
        return "missed_retry" if attempt <= 1 else "missed_twice"
    if outcome == "dropped":
        if "slipped" in reason:
            return "dropped_slipped"
        if "still holding" in reason:
            return "dropped_timeout"
        return "dropped_wrong_place"
    return "error"


# ---------------------------------------------------------------------------
# ElevenLabs


def _api_key():
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise VoiceError(
            f"{KEY_VARIABLE} is not set. Create a key in your ElevenLabs account, then run:\n"
            f"    export {KEY_VARIABLE}=<your key>\n"
            "Keep the key out of config.json and out of git."
        )
    return key


def _request(url, api_key, body=None, timeout=60):
    headers = {"xi-api-key": api_key}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        message = f"HTTP {error.code}"
        try:
            detail = json.loads(error.read().decode()).get("detail")
            if isinstance(detail, dict):
                message = detail.get("message") or message
            elif detail:
                message = str(detail)
        except (ValueError, AttributeError):
            pass
        raise VoiceError(f"ElevenLabs refused the request: {message}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise VoiceError(f"could not reach ElevenLabs: {getattr(error, 'reason', error)}") from None


def synthesize(text, settings, api_key):
    """Turn one sentence into audio with the ElevenLabs text-to-speech API. Returns the file's bytes."""
    if not settings.voice_id:
        raise VoiceError("no voice chosen. List them with 'python -m kitcheck.voice voices', then pass --voice <id>.")
    url = (
        f"{API}/v1/text-to-speech/{urllib.parse.quote(settings.voice_id)}"
        f"?output_format={urllib.parse.quote(settings.output_format)}"
    )
    return _request(url, api_key, {"text": text, "model_id": settings.model_id})


def list_voices(api_key, pages=5):
    """Voices available to the account: (name, voice id, category)."""
    voices, token = [], None
    for _ in range(pages):
        url = f"{API}/v2/voices?page_size=100"
        if token:
            url += f"&next_page_token={urllib.parse.quote(token)}"
        reply = json.loads(_request(url, api_key).decode())
        voices += [(v.get("name", ""), v.get("voice_id", ""), v.get("category", "")) for v in reply.get("voices", [])]
        token = reply.get("next_page_token")
        if not reply.get("has_more") or not token:
            break
    return voices


# ---------------------------------------------------------------------------
# Making and finding clips


def read_index(settings):
    path = Path(settings.clips) / INDEX
    if not path.is_file():
        return {"voice_id": "", "model_id": "", "output_format": "", "clips": {}}
    return json.loads(path.read_text())


def build(settings, api_key=None, force=False, make=synthesize, report=print):
    """Make every clip that is missing or out of date. Returns (made, kept, characters sent)."""
    folder = Path(settings.clips)
    folder.mkdir(parents=True, exist_ok=True)
    index = read_index(settings)
    same_voice = (
        index.get("voice_id") == settings.voice_id
        and index.get("model_id") == settings.model_id
        and index.get("output_format") == settings.output_format
    )
    clips = index.get("clips", {}) if same_voice else {}
    made = kept = characters = 0
    for name, text, file_name in lines(settings):
        entry = clips.get(name)
        current = entry and entry.get("text") == text and (folder / entry.get("file", "")).is_file()
        if current and not force:
            kept += 1
            continue
        if api_key is None:
            api_key = _api_key()
        audio = make(text, settings, api_key)
        temporary = folder / (file_name + ".part")
        temporary.write_bytes(audio)
        temporary.replace(folder / file_name)
        clips[name] = {"text": text, "file": file_name}
        made += 1
        characters += len(text)
        report(f"  made {file_name}: {text}")
        # Save after every clip, so an interrupted build keeps what it has made.
        _write_index(settings, clips)
    wanted = {name for name, _, _ in lines(settings)}
    clips = {name: entry for name, entry in clips.items() if name in wanted}
    _write_index(settings, clips)
    return made, kept, characters


def _write_index(settings, clips):
    index = {
        "voice_id": settings.voice_id,
        "model_id": settings.model_id,
        "output_format": settings.output_format,
        "clips": clips,
    }
    path = Path(settings.clips) / INDEX
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(index, indent=2) + "\n")
    temporary.replace(path)


def find_player():
    """A command that plays an audio file and exits, or None. KITCHECK_PLAYER overrides."""
    custom = os.environ.get("KITCHECK_PLAYER", "").strip()
    if custom:
        return custom.split()
    for command in (
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],  # comes with ffmpeg
        ["mpg123", "-q"],
        ["afplay"],                                                 # macOS
        ["mpv", "--really-quiet", "--no-video"],
    ):
        if shutil.which(command[0]):
            return command
    return None


class Voice:
    """Plays saved clips. Never raises and never needs the network: a station that cannot speak still works."""

    def __init__(self, settings=None, player=None, start=subprocess.Popen):
        self.settings = settings or Settings()
        self._player = player
        self._start = start
        self._playing = None
        try:
            self._clips = read_index(self.settings).get("clips", {})
        except (OSError, ValueError):
            self._clips = {}

    @classmethod
    def from_config(cls, path="config.json"):
        try:
            return cls(Settings.from_config(path))
        except (OSError, ValueError):
            return cls(Settings())

    def clip_for(self, key, item=None):
        """Path of the saved clip for a phrase, or None. The order page can serve this file."""
        if key not in PHRASES or (needs_item(key) and not item):
            return None
        entry = self._clips.get(clip_name(key, item))
        if not entry:
            return None
        path = Path(self.settings.clips) / entry.get("file", "")
        return path if path.is_file() else None

    def say(self, key, item=None, wait=False):
        """Play a phrase if voice is on and its clip exists. Returns True if playback started."""
        try:
            if not self.settings.enabled:
                return False
            path = self.clip_for(key, item)
            if path is None:
                return False
            player = self._player or find_player()
            if not player:
                return False
            if self._playing is not None and self._playing.poll() is None:
                self._playing.terminate()  # do not talk over the previous line
            self._playing = self._start(
                list(player) + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if wait:
                return self._playing.wait(timeout=15) == 0  # False if the player could not play it
            return True
        except Exception:  # noqa: BLE001 - speech must never break a pick
            return False


# ---------------------------------------------------------------------------
# Command line


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m kitcheck.voice", description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="config.json", help="settings file (default: config.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="what the station can say, and which clips exist")
    sub.add_parser("voices", help="voices available to your ElevenLabs account")
    p = sub.add_parser("build", help="make every missing clip with the ElevenLabs API")
    p.add_argument("--voice", help="voice id (otherwise voice.voice_id from config.json)")
    p.add_argument("--model", help=f"model id (default {DEFAULT_MODEL})")
    p.add_argument("--force", action="store_true", help="make every clip again")
    p = sub.add_parser("say", help="play one saved clip")
    p.add_argument("key", choices=sorted(PHRASES))
    p.add_argument("--item")
    args = parser.parse_args(argv)

    settings = Settings.from_config(args.config)
    try:
        if args.command == "list":
            voice = Voice(settings)
            ready = 0
            for name, text, _ in lines(settings):
                key, _, item = name.partition(":")
                have = voice.clip_for(key, item or None) is not None
                ready += have
                print(f"{'ready  ' if have else 'missing'}  {name:<28} {text}")
            total = len(lines(settings))
            print(f"\n{ready} of {total} clips ready in {settings.clips}; voice is {'on' if settings.enabled else 'off'} in {args.config}")
            return 0

        if args.command == "voices":
            for name, voice_id, category in sorted(list_voices(_api_key())):
                print(f"{voice_id}  {category:<12} {name}")
            return 0

        if args.command == "build":
            if args.voice:
                settings.voice_id = args.voice
            if args.model:
                settings.model_id = args.model
            if not settings.voice_id:
                settings.voice_id = read_index(settings).get("voice_id", "")
            if not settings.voice_id:
                raise VoiceError("no voice chosen. Run 'python -m kitcheck.voice voices' and pass --voice <id>.")
            made, kept, characters = build(settings, force=args.force)
            print(f"\nmade {made} clips ({characters} characters sent), kept {kept}, in {settings.clips}")
            if not settings.enabled:
                print(f'To hear them during runs, set "voice": {{"enabled": true}} in {args.config}.')
            return 0

        settings.enabled = True  # 'say' is a direct request to play
        voice = Voice(settings)
        if voice.clip_for(args.key, args.item) is None:
            raise VoiceError(
                f"no clip for '{args.key}'" + (f" with item '{args.item}'" if args.item else "")
                + ". Run 'python -m kitcheck.voice list' to see what exists."
            )
        if find_player() is None:
            raise VoiceError("no audio player found. Install ffmpeg (for ffplay) or set KITCHECK_PLAYER.")
        if not voice.say(args.key, args.item, wait=True):
            raise VoiceError(
                f"the audio player could not play {voice.clip_for(args.key, args.item)}. "
                "Check the speaker, or set KITCHECK_PLAYER to another player."
            )
        return 0
    except VoiceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
