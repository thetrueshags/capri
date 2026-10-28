# Your seed prompt

`persona.template.txt` is a zero-byte public template. Setup or first launch copies
it to `data/persona.txt` without overwriting an existing local prompt.

Edit **your local `data/persona.txt`**, using Settings → Edit my seed prompt or a text
editor. This file is ignored by Git. Do not put your personal prompt in the tracked
template if you intend to share the repository.

There is no required format. You can write any combination of:

- Identity and conversational tone.
- Values, boundaries and preferences.
- Energy, curiosity, playfulness, affection, patience and personal space.

These are suggestions for what you may fill in; the distributed template contains
none of them. A blank prompt uses the app's generic Capri identity and neutral
desktop traits. Application instructions about memory records, current observations
and bounded decisions still apply independently of personality.

Chat reads the prompt fresh for each request. Body behavior notices edits in the
background and asks the selected local model to infer six bounded style traits.
When the model is unavailable, it retains its last valid profile. Clearing the
prompt deliberately returns body traits to neutral without model inference.

The app does not promise that a small language model will interpret every prompt
exactly. The chat header reports synchronization status. You can disable personality
behavior in Settings while keeping animations, chat and mouse reactions.

## Settings and animation

Settings includes the installed model name, roaming, quiet mode, pointer awareness,
mouse reactions, media avoidance and automatic media watching.

`data/config.json` also holds loop selection intervals, transition duration, size,
sleep delay and protected monitor keys. Close Capri before editing it manually.

Prepared frames and their millisecond hold times are in
`assets/companion/animations.json`; transitions are in `transitions.json` beside it.
Keep the common frame canvas and anchor when replacing artwork. Body loops repeat
until the controller selects another expression, even when source metadata suggests
a one-shot reaction. The transition plays once and relocates during its eye-box-only
frames. Earlier/later activity poses blend with the seated transition's bookends.

The media animation is mirrored for the opposite screen edge. Music, reading and
other manual previews are expressions, not claims to detect the corresponding
content. Right-click → Animation library offers every non-transition library clip.

## Separate profiles

Set `CAPRI_DATA_DIR` before setup/launch, or pass `--profile` to the Python entry
point, to use another data directory. Each profile has its own prompt, memories,
configuration and process lock. Keep custom data directories outside the Git repo
or add them to `.gitignore` yourself.
