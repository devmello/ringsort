# 10. Voice (optional)

The station can say what it is doing, in a voice made with the ElevenLabs API: "Picking the sensor." "I picked up nothing. Trying again." "Kit ready." It is an option, it is off by default, and it is the last thing to switch on.

| Piece | File | Status |
|---|---|---|
| Phrases, clip making, playback | `kitcheck/voice.py` | Written. Tested with stand-ins for the API and the speaker. |
| Spoken verdict after a test pick | `scripts/try_model.sh` | Written. Silent unless voice is on. |
| Speaking during an order | `kitcheck/runner.py` | Design only, like the rest of the runner |

No clip has been made with a real key yet, so the voice itself is unheard.

## Why it is worth having

- **It suits the station.** Your eyes and hands are on the cubes. A station that says "Please put a motor on its square" does not need you to watch the screen.
- **It makes the self-check audible.** When you steal a cube in the demo, the judge hears "I picked up nothing. Trying again." without reading anything.
- **It uses a sponsor's API** without putting the demo at the mercy of the venue's Wi-Fi.

## How it stays offline

Everything the station can say is known in advance: 25 lines with two item types. So the clips are made once, while online, and saved in `assets/voice/`. While the station runs it only plays those files. No key and no network are needed during a demo, and "no cloud calls at demo time" stays true.

`assets/voice/` is kept in git, so clips made on one machine travel with the project. The PC never needs your key.

## Switching it on

About five minutes, on any machine that is online. Do it during the event, so the audio is event work.

1. **Get a key.** Create an API key in your ElevenLabs account. In the terminal:

```shell
export ELEVENLABS_API_KEY=<your key>
```

2. **Choose a voice.**

```shell
python -m kitcheck.voice voices
```

It lists the voices your account can use, with their IDs. ElevenLabs' own examples use the ID `JBFqnCBsd6RMkjVDRZzb`, which is a quick first try if it is in your list.

3. **Make the clips.**

```shell
python -m kitcheck.voice build --voice <voice id>
```

It prints each line as it makes it. The full set is about 1,000 characters; check that against the allowance on your plan. Running it again only makes what is missing.

4. **Listen.**

```shell
python -m kitcheck.voice say kit_ready
python -m kitcheck.voice say picking --item sensor
python -m kitcheck.voice list
```

5. **Turn it on.** In `config.json`:

```json
"voice": {"enabled": true, "voice_id": "<voice id>", "model_id": "eleven_multilingual_v2", "clips": "assets/voice"}
```

From then on `bash scripts/try_model.sh sensor` speaks its verdict after each pick, and the runner will speak during orders once it is written.

Run the commands from the project folder.

## What it says

| Phrase | Line | When |
|---|---|---|
| `hello` | KitCheck is ready. Choose a kit. | Start-up; also a speaker test |
| `order_started` | Order received. Packing your kit. | An order is accepted |
| `picking` | Picking the sensor. | A skill starts |
| `verified` | Sensor placed. | The checks agree it is in |
| `missed` | I picked up nothing. | A single test pick that missed |
| `missed_retry` | I picked up nothing. Trying again. | First miss in an order |
| `missed_twice` | I picked up nothing twice. Is there a sensor on its square? | Second miss |
| `dropped_slipped` | The sensor slipped out of my gripper. I need a hand. | The grasp check saw a slip |
| `dropped_wrong_place` | I let go of the sensor away from the tray. I need a hand. | Released in the wrong place |
| `dropped_timeout` | I ran out of time while holding the sensor. I need a hand. | Still holding at the time limit |
| `error` | The robot run failed. Please check the screen. | A run failed |
| `restock` | Please put a sensor on its square. | Camera check: square empty |
| `unconfirmed` | I let go at the tray, but I can't see a new sensor in it. | Camera check disagrees |
| `incomplete` | The kit is incomplete. A sensor is missing. | Camera check: item removed |
| `kit_ready` | Kit ready. | Every item verified |
| `collected` | Kit collected. Thank you. | Camera check: tray emptied |

Lines that name an item are made once per item, using the item labels in `config.json`. To change the wording, edit `PHRASES` in `kitcheck/voice.py` and run `build` again; only the changed lines are remade.

## Where the sound comes out

`kitcheck/voice.py` plays clips with the first of these it finds: `ffplay` (it comes with ffmpeg, which LeRobot needs anyway), `mpg123`, `afplay` on a Mac, or `mpv`. Set `KITCHECK_PLAYER` to use something else.

The PC needs a speaker: a monitor with speakers, or a small speaker in the headphone socket. Test it at hall volume, not desk volume.

## Where it plugs in

**Today, with no more code:** `scripts/try_model.sh` speaks the grasp check's verdict after every test pick.

**In the runner (to write):** one call at each state change.

```python
from kitcheck.voice import Voice, key_for_verdict

voice = Voice.from_config()          # reads config.json; does nothing if voice is off
voice.say("picking", item)
voice.say(key_for_verdict(verdict.outcome, verdict.reason, attempt), item)
voice.say("kit_ready")
```

`say` never raises and never waits for the network. If voice is off, a clip is missing or no player is found, it returns `False` and the order carries on.

**On the order page (to write, optional):** the page can play the same files itself, so the sound comes from whichever device is showing the page. `Voice.clip_for(...)` gives the file; doc 7 has the outline. Play each line in one place only, the PC or the page, not both.

## Adding an item

Add the item to `config.json`, then run `build` again with the key set. Only the new item's lines are made.

## Keeping the key safe

- The key lives in your terminal's environment, nowhere else. `kitcheck/voice.py` never writes it to a file or prints it.
- Do not put it in `config.json` or `scripts/settings.env`. `scripts/secrets.env` and `.env` are ignored by git if you want a private file to load it from.
- Prefer making the clips on your own laptop over typing the key into a shared PC.

## Later, if there is time and reason

Both of these call ElevenLabs while the station runs, so the demo would then depend on the network:

- **Free-form speech.** Speaking a sentence that was not prepared, such as a typed order read back. `synthesize()` in `kitcheck/voice.py` already makes one clip from any text; the low-latency models suit this better than the default.
- **Spoken orders.** ElevenLabs has a speech-to-text endpoint. Voice input stays cut from the plan because a hackathon hall is loud.

## What to say about it, and what not to

- **Say:** the station speaks its status with an ElevenLabs voice; the lines are made ahead of time with their text-to-speech API and played locally, which is why it works with no connection.
- **Do not say** it is a conversation, that it listens, or that speech is generated live.
- If you are entering a sponsor prize, read its rules first.

## How this doc was checked

- The request follows ElevenLabs' current API reference: `POST /v1/text-to-speech/{voice_id}` with the `xi-api-key` header, default model `eleven_multilingual_v2`, default format `mp3_44100_128`; voices from `GET /v2/voices`.
- A real request with a wrong key reached ElevenLabs and came back as "Invalid API key", which the tool reports plainly.
- Making clips, keeping them, remaking only what changed, playing them and staying silent on every failure were tested with stand-ins: `python tests/test_voice.py`.
- No request with a valid key was made. No real clip exists yet.
