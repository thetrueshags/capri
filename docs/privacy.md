# Local data

The default profile is `data/` in the project folder. Git ignores it.

| File | Contents |
| --- | --- |
| `persona.txt` | Your private seed prompt |
| `config.json` | Local settings and model name |
| `capri-memory.sqlite3` | Chats, explicit memory notes and activity metadata |
| `behavior-profile.json` | Last inferred style traits and prompt/model hash |
| `runtime.log` | Rotating error log |
| `inbox/` | Temporary activity events waiting to be consumed |

Chats persist. Facts are explicit notes, not automatic claims about the user.
Use `/remember text`, `/memories`, `/forget ID` and `/clear`, or the Memory tab.
Deleting a fact does not remove earlier chat text containing it; clear chat
separately when needed. The Memory tab can export a journal to a location you choose.

Capri reads global pointer position and monitor geometry for mouse reactions.
It does not save a pointer trail. Chat receives a labeled current cursor/sprite
snapshot; a saved spoken answer may mention that observation.

Media detection reads window titles, app names, monitor locations and Windows
playback metadata. Titles stay transient. Watch start/stop journal events record
only an app name and state. No media frames or audio are captured.

Microphone access, screen capture, browser history reading and computer control
are not implemented. Capri does not click or move the mouse. Model requests go
to the configured loopback Ollama service. Verify the runtime/model you install
independently if you have additional privacy requirements.

Error logs can contain exception details and local paths. Inspect logs and memory
exports before attaching them to a public issue. The activity bridge discards prompts,
arguments, tool output and transcript paths; it retains metadata only.

Before sharing a fork, run `python tools/check_release.py` and inspect `git status`.
Ignored files are still present locally, and `git add -f` can override ignores.
