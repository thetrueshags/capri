# Software activity

Capri consumes local atomic event files. There is no network listener.
The supported states are `idle`, `working`, `waiting`, `ready` and `blocked`.

From PowerShell, call the script using your checkout's path:

```powershell
& './Send-CapriEvent.ps1' -State working -Source build -Session demo -Project example
& './Send-CapriEvent.ps1' -State ready -Source build -Session demo -Project example
```

Use distinct session IDs for parallel tasks. Waiting and blocked sessions take
priority; stale busy states expire. The Activity tab has demo buttons for testing.
Choose the same `CAPRI_DATA_DIR` for the pet and event sender when using another profile.

## Optional Codex launcher

From the project you are working on, invoke the absolute path to
`Start-Codex-With-Capri.ps1` in this checkout. It preserves your working directory
and accepts additional Codex arguments, including `resume`.

The launcher supplies observational hooks to that new Codex invocation; it does not
modify global Codex settings or instrument existing sessions. New hook definitions
require review/trust in Codex's `/hooks` interface. Review the generated bridge
commands before trusting them. Managed policy may prohibit hooks. The launcher
does not bypass trust or approval controls. Hook support depends on your installed
Codex version; the desktop app does not require Codex.

Session start/end, prompt/tool activity, permission requests, structured tool errors
and completion map to desktop states. The bridge strips prompts, arguments, output
and transcript paths before persistence. Not all tool failures have a structured
error flag; hooks are activity signals rather than full process monitoring.
